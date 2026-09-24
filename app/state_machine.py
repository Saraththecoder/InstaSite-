import logging
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.models import Business, Product, Change, ChangeAction
from app.schemas.intent import IntentResult, IntentType
from app.generator import generate_storefront, slugify

logger = logging.getLogger(__name__)


def find_business_by_owner(session: Session, owner_telegram_id: int) -> Optional[Business]:
    """Find the most recent business for this owner."""
    return (
        session.query(Business)
        .filter(Business.owner_telegram_id == owner_telegram_id)
        .order_by(desc(Business.business_id))
        .first()
    )


def match_product(session: Session, business_id: int, query_name: str) -> Optional[Product]:
    """
    Fuzzy/substring match product name within this business.
    e.g. 'biryani' matches 'Chicken Biryani' or 'biryani'.
    """
    products = session.query(Product).filter(Product.business_id == business_id).all()
    q = query_name.lower().strip()

    # Exact match first
    for p in products:
        if p.name.lower() == q:
            return p

    # Substring match (q in product name or product name in q)
    for p in products:
        if q in p.name.lower() or p.name.lower() in q:
            return p

    # Word intersection match
    q_words = set(q.split())
    for p in products:
        p_words = set(p.name.lower().split())
        if q_words & p_words:
            return p

    return None


def propose_change(
    session: Session,
    owner_telegram_id: int,
    intent_result: IntentResult,
    image_url: Optional[str] = None,
) -> Tuple[Optional[Change], str]:
    """
    Creates a pending change record in `changes` with confirmed=False.
    Returns (change_obj, human_readable_summary).
    Does NOT mutate businesses or products.
    """
    action_type = intent_result.intent

    if action_type == IntentType.CREATE_BUSINESS:
        shop_name = intent_result.shop_name or "My Restaurant"
        products_data = [{"name": p.name, "price": p.price} for p in intent_result.products]

        change = Change(
            action=ChangeAction.CREATE_BUSINESS,
            business_id=None,
            product_id=None,
            old_value=None,
            new_value={
                "owner_telegram_id": owner_telegram_id,
                "business_name": shop_name,
                "category": "Restaurant",
                "products": products_data,
            },
            confirmed=False,
            reversed=False,
        )
        session.add(change)
        session.commit()
        session.refresh(change)

        # Human-readable summary for Telegram confirmation card
        summary_lines = [f"🏪 *{shop_name}* (Restaurant)"]
        if products_data:
            summary_lines.append("Menu items:")
            for p in products_data:
                price_str = f"₹{int(p['price'])}" if float(p['price']).is_integer() else f"₹{p['price']:.2f}"
                summary_lines.append(f"  • {p['name']}: {price_str}")
        summary_lines.append("\nCreate this storefront?")
        return change, "\n".join(summary_lines)

    elif action_type == IntentType.ADD_PRODUCT:
        biz = find_business_by_owner(session, owner_telegram_id)
        if not biz:
            return None, "You don't have a storefront yet! Send a voice note with your shop name and dishes to create one."

        prod_name = intent_result.product_name or "New Dish"
        price = intent_result.new_price or 0.0
        price_str = f"₹{int(price)}" if float(price).is_integer() else f"₹{price:.2f}"

        new_val = {"name": prod_name, "price": price}
        if image_url:
            new_val["image_url"] = image_url

        change = Change(
            action=ChangeAction.ADD_PRODUCT,
            business_id=biz.business_id,
            product_id=None,
            old_value=None,
            new_value=new_val,
            confirmed=False,
            reversed=False,
        )
        session.add(change)
        session.commit()
        session.refresh(change)

        photo_label = " (with photo)" if image_url else ""
        summary = f"Add *{prod_name}*{photo_label} at {price_str} to your menu. Publish?"
        return change, summary

    elif action_type == IntentType.UPDATE_PRICE:
        biz = find_business_by_owner(session, owner_telegram_id)
        if not biz:
            return None, "You don't have a storefront yet! Send a voice note with your shop name and dishes to create one."

        query_name = intent_result.product_name or ""
        product = match_product(session, biz.business_id, query_name)
        if not product:
            return None, f"Could not find a dish matching '{query_name}' in your menu."

        old_price = product.price
        new_price = intent_result.new_price or 0.0

        old_str = f"₹{int(old_price)}" if float(old_price).is_integer() else f"₹{old_price:.2f}"
        new_str = f"₹{int(new_price)}" if float(new_price).is_integer() else f"₹{new_price:.2f}"

        change = Change(
            action=ChangeAction.UPDATE_PRICE,
            business_id=biz.business_id,
            product_id=product.product_id,
            old_value={"name": product.name, "price": old_price},
            new_value={"name": product.name, "price": new_price},
            confirmed=False,
            reversed=False,
        )
        session.add(change)
        session.commit()
        session.refresh(change)

        summary = f"{product.name}: {old_str} → {new_str}. Publish?"
        return change, summary

    return None, "Action does not require confirmation."


def confirm_change(session: Session, change_id: int) -> Tuple[bool, str, Optional[str]]:
    """
    Sets confirmed=True, applies the mutation to businesses/products,
    and triggers static storefront regeneration.
    Returns (success, message, web_path).
    """
    change = session.query(Change).filter(Change.change_id == change_id).first()
    if not change:
        return False, "Change request not found.", None
    if change.confirmed:
        return False, "This change was already confirmed.", None

    if change.action == ChangeAction.CREATE_BUSINESS:
        data = change.new_value
        owner_id = data["owner_telegram_id"]
        biz_name = data["business_name"]
        slug = slugify(biz_name)

        # Ensure slug uniqueness
        existing_slug = session.query(Business).filter(Business.slug == slug).first()
        if existing_slug and existing_slug.owner_telegram_id != owner_id:
            slug = f"{slug}-{owner_id}"

        logo_url = data.get("logo_url")
        hero_image_url = data.get("hero_image_url")

        # Auto-generate hero image if not already generated
        if not hero_image_url:
            try:
                from app.hero_generator import generate_hero_banner
                from app.config import BASE_DIR
                local_logo = str(BASE_DIR / logo_url.lstrip("/")) if logo_url else None
                hero_path = BASE_DIR / "static" / "images" / "heroes" / f"{slug}_hero.jpg"
                generate_hero_banner(
                    business_name=biz_name,
                    category=data.get("category", "Store"),
                    tagline=data.get("tagline"),
                    logo_path=local_logo,
                    output_path=hero_path,
                )
                hero_image_url = f"/static/images/heroes/{slug}_hero.jpg"
            except Exception as e:
                logger.warning(f"Hero generation fallback: {e}")

        # Check if owner already has a business with this slug
        business = session.query(Business).filter(Business.owner_telegram_id == owner_id, Business.slug == slug).first()
        if not business:
            business = Business(
                owner_telegram_id=owner_id,
                business_name=biz_name,
                category=data.get("category", "Shop / Retail Store"),
                tagline=data.get("tagline"),
                about_us=data.get("about_us"),
                trust_badges=data.get("trust_badges"),
                phone=data.get("phone"),
                whatsapp=data.get("whatsapp"),
                address=data.get("address"),
                opening_hours=data.get("opening_hours"),
                cta_text=data.get("cta_text", "Book Now"),
                logo_url=logo_url,
                hero_image_url=hero_image_url,
                slug=slug,
            )
            session.add(business)
            session.flush()
        else:
            if data.get("tagline"): business.tagline = data.get("tagline")
            if data.get("about_us"): business.about_us = data.get("about_us")
            if data.get("trust_badges"): business.trust_badges = data.get("trust_badges")
            if data.get("phone"): business.phone = data.get("phone")
            if data.get("whatsapp"): business.whatsapp = data.get("whatsapp")
            if data.get("address"): business.address = data.get("address")
            if data.get("opening_hours"): business.opening_hours = data.get("opening_hours")
            if data.get("cta_text"): business.cta_text = data.get("cta_text")
            if logo_url: business.logo_url = logo_url
            if hero_image_url: business.hero_image_url = hero_image_url

        change.business_id = business.business_id

        # Insert products
        for p in data.get("products", []):
            img = p.get("image_url")
            product = Product(
                business_id=business.business_id,
                name=p["name"],
                price=float(p["price"]),
                image_url=img,
                is_placeholder=False if img else True,
            )
            session.add(product)

        change.confirmed = True
        session.commit()

        # Regenerate storefront
        _, web_path = generate_storefront(business.business_id, session)
        return True, f"Storefront created: {web_path}", web_path

    elif change.action == ChangeAction.ADD_PRODUCT:
        data = change.new_value
        img = data.get("image_url")
        product = Product(
            business_id=change.business_id,
            name=data["name"],
            price=float(data["price"]),
            image_url=img,
            is_placeholder=False if img else True,
        )
        session.add(product)
        session.flush()

        change.product_id = product.product_id
        change.confirmed = True
        session.commit()

        _, web_path = generate_storefront(change.business_id, session)
        return True, "Updated.", web_path

    elif change.action == ChangeAction.UPDATE_PRICE:
        product = session.query(Product).filter(Product.product_id == change.product_id).first()
        if not product:
            return False, "Product not found.", None

        product.price = float(change.new_value["price"])
        change.confirmed = True
        session.commit()

        _, web_path = generate_storefront(change.business_id, session)
        return True, "Updated.", web_path

    return False, "Unknown action.", None


def reject_change(session: Session, change_id: int) -> str:
    """
    Cancels a pending change without applying any mutation to the database.
    Leaves confirmed=False (or deletes the pending change row).
    """
    change = session.query(Change).filter(Change.change_id == change_id).first()
    if change and not change.confirmed:
        session.delete(change)
        session.commit()
    return "Change cancelled. Nothing was updated."


def undo_last_change(session: Session, owner_telegram_id: int) -> Tuple[bool, str, Optional[str]]:
    """
    Single-level undo:
    Finds the most recent row in changes where confirmed=True AND reversed=False for this business,
    applies old_value back, sets reversed=True, and regenerates the storefront.
    No snapshot table.
    """
    biz = find_business_by_owner(session, owner_telegram_id)
    if not biz:
        return False, "No business found for your account.", None

    last_change = (
        session.query(Change)
        .filter(
            Change.business_id == biz.business_id,
            Change.confirmed == True,
            Change.reversed == False,
        )
        .order_by(desc(Change.timestamp), desc(Change.change_id))
        .first()
    )

    if not last_change:
        return False, "No recent confirmed changes to undo.", None

    if last_change.action == ChangeAction.UPDATE_PRICE:
        product = session.query(Product).filter(Product.product_id == last_change.product_id).first()
        if not product:
            return False, "Associated product no longer exists.", None

        old_p = float(last_change.old_value["price"])
        product.price = old_p
        last_change.reversed = True
        session.commit()

        _, web_path = generate_storefront(biz.business_id, session)
        old_str = f"₹{int(old_p)}" if old_p.is_integer() else f"₹{old_p:.2f}"
        return True, f"Reverted {product.name} to {old_str}.", web_path

    elif last_change.action == ChangeAction.ADD_PRODUCT:
        product = session.query(Product).filter(Product.product_id == last_change.product_id).first()
        if product:
            session.delete(product)
        last_change.reversed = True
        session.commit()

        _, web_path = generate_storefront(biz.business_id, session)
        return True, f"Reverted addition of {last_change.new_value['name']}.", web_path

    elif last_change.action == ChangeAction.CREATE_BUSINESS:
        # Mark reversed
        last_change.reversed = True
        session.commit()
        return True, "Reverted storefront creation.", None

    return False, "Cannot undo this change type.", None
