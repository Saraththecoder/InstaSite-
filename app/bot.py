import os
import re
import uuid
import tempfile
import logging
from typing import Optional, Any
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from app.config import require_telegram_token, STORE_BASE_URL, BASE_DIR
from app.db.database import SessionLocal, init_db
from app.stt import transcribe_audio
from app.extract import extract_business_from_transcript
from app.intent import route_intent, handle_intent_confidence_gate
from app.schemas.intent import IntentType, IntentResult
from app.db.models import Change, ChangeAction
from app.state_machine import (
    find_business_by_owner,
    propose_change,
    confirm_change,
    reject_change,
    undo_last_change,
)
from app.generator import slugify
from app.hero_generator import generate_hero_banner, generate_brand_monogram

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def sync_vercel_deployment() -> str | None:
    """Deploys updated stores to Vercel if VERCEL_TOKEN is configured."""
    try:
        from deploy_vercel import deploy_to_vercel
        return deploy_to_vercel()
    except Exception as e:
        logger.warning(f"Vercel auto-deploy skipped/failed: {e}")
        return None


# Conversation states for the step-by-step questionnaire
(
    ASK_NAME,
    ASK_TYPE,
    ASK_TAGLINE,
    ASK_ABOUT,
    ASK_TRUST,
    ASK_PHONE,
    ASK_WHATSAPP,
    ASK_ADDRESS,
    ASK_HOURS,
    ASK_CTA,
    ASK_LOGO,
    ASK_PROD_NAME,
    ASK_PROD_PHOTO,
    ASK_PROD_PRICE,
) = range(14)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start command."""
    welcome_text = (
        "Namaste! 🙏 Welcome to *DukaanMitra AI*.\n\n"
        "I build and publish modern digital storefronts for your business!\n\n"
        "✨ *How would you like to create your website?*\n\n"
        "1️⃣ *Step-by-step Guide*: Send /create and I will ask you 11 quick questions.\n"
        "2️⃣ *Instant Voice/Text*: Send a voice note or message like:\n"
        "`My shop is Paradise. Chicken Biryani 250, Chicken 65 180`\n\n"
        "⚡ *Commands*:\n"
        "• `/create` - Start step-by-step questionnaire\n"
        "• `/undo` - Revert last change\n"
        "• `show my business` - View your live website"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


# =========================================================================
# Step-by-Step Questionnaire Wizard
# =========================================================================

async def start_create_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for /create step-by-step questionnaire."""
    context.user_data["biz"] = {}
    await update.message.reply_text(
        "🚀 *Let's build your website step-by-step!*\n\n"
        "1️⃣ *What is your Business Name?*\n"
        "(e.g. `Apex Auto Care` or `Paradise`)",
        parse_mode="Markdown"
    )
    return ASK_NAME


async def ask_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data["biz"]["business_name"] = name
    await update.message.reply_text(
        f"Great! Setting up *{name}*.\n\n"
        "2️⃣ *What is your Business Type?*\n"
        "(e.g. `Shop / Retail Store`, `Auto Care`, `Restaurant`, `Salon`)",
        parse_mode="Markdown"
    )
    return ASK_TYPE


async def ask_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btype = update.message.text.strip()
    context.user_data["biz"]["category"] = btype
    await update.message.reply_text(
        "3️⃣ *Tagline / Motto?*\n"
        "(e.g. `Precision vehicle repair & detailing` or type `skip`)",
        parse_mode="Markdown"
    )
    return ASK_TAGLINE


async def ask_tagline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    context.user_data["biz"]["tagline"] = "" if txt.lower() == "skip" else txt
    await update.message.reply_text(
        "4️⃣ *About Us (Story & Mission)?*\n"
        "(e.g. `Family-owned business serving Springfield since 2010. We pride ourselves on transparent pricing and unmatched craft.` or type `skip`)",
        parse_mode="Markdown"
    )
    return ASK_ABOUT


async def ask_about_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    context.user_data["biz"]["about_us"] = "" if txt.lower() == "skip" else txt
    await update.message.reply_text(
        "5️⃣ *Trust Elements / Badges?*\n"
        "(e.g. `100% Satisfaction Guarantee, 5000+ Happy Clients, Licensed & Insured` or type `skip`)",
        parse_mode="Markdown"
    )
    return ASK_TRUST


async def ask_trust_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    context.user_data["biz"]["trust_badges"] = "" if txt.lower() == "skip" else txt
    await update.message.reply_text(
        "6️⃣ *Phone Number?*\n"
        "(e.g. `+1 555 123 4567` or type `skip`)",
        parse_mode="Markdown"
    )
    return ASK_PHONE


async def ask_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    context.user_data["biz"]["phone"] = "" if txt.lower() == "skip" else txt
    await update.message.reply_text(
        "7️⃣ *WhatsApp Number?*\n"
        "(e.g. `+1 555 123 4567`, `same`, or `skip`)",
        parse_mode="Markdown"
    )
    return ASK_WHATSAPP


async def ask_whatsapp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt.lower() == "same":
        wa = context.user_data["biz"].get("phone", "")
    elif txt.lower() == "skip":
        wa = ""
    else:
        wa = txt
    context.user_data["biz"]["whatsapp"] = wa
    await update.message.reply_text(
        "8️⃣ *Address / Location?*\n"
        "(e.g. `123 Main Street, Suite 4B` or type `skip`)",
        parse_mode="Markdown"
    )
    return ASK_ADDRESS


async def ask_address_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    context.user_data["biz"]["address"] = "" if txt.lower() == "skip" else txt
    await update.message.reply_text(
        "9️⃣ *Operating Hours?*\n"
        "(e.g. `Mon-Fri 8am-6pm, Sat 9am-4pm` or type `skip`)",
        parse_mode="Markdown"
    )
    return ASK_HOURS


async def ask_hours_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    context.user_data["biz"]["opening_hours"] = "" if txt.lower() == "skip" else txt
    await update.message.reply_text(
        "🔟 *Call to Action (Button Text)?*\n"
        "(e.g. `Book Inspection Now`, `Order Online`, `Call Us`)",
        parse_mode="Markdown"
    )
    return ASK_CTA


async def ask_cta_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    context.user_data["biz"]["cta_text"] = "Book Now" if txt.lower() == "skip" else txt
    await update.message.reply_text(
        "1️⃣1️⃣ *Business Logo*\n\n"
        "📸 Please upload or send your **Business Logo** image:\n"
        "*(Or send /skip to automatically generate a branded monogram logo)*",
        parse_mode="Markdown"
    )
    return ASK_LOGO


async def ask_logo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    biz_data = context.user_data.get("biz", {})
    slug = slugify(biz_data.get("business_name", "shop"))

    logo_url = None
    photo_file = None
    if update.message.photo:
        photo_file = update.message.photo[-1]
    elif update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("image/"):
        photo_file = update.message.document

    if photo_file:
        try:
            file_obj = await context.bot.get_file(photo_file.file_id)
            img_dir = BASE_DIR / "static" / "images" / "logos"
            img_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{slug}_logo.jpg"
            dest_path = img_dir / filename
            await file_obj.download_to_drive(custom_path=str(dest_path))
            logo_url = f"/static/images/logos/{filename}"
            await update.message.reply_text("✅ Logo received!")
        except Exception as e:
            logger.error(f"Failed to download logo: {e}", exc_info=True)
    elif update.message.text and update.message.text.strip().lower() in ["skip", "/skip", "no", "none"]:
        return await skip_logo_handler(update, context)
    else:
        await update.message.reply_text(
            "Please send an image photo for your logo, or type `/skip`.",
            parse_mode="Markdown"
        )
        return ASK_LOGO

    biz_data["logo_url"] = logo_url

    # Generate custom hero banner based on context and logo!
    try:
        hero_dir = BASE_DIR / "static" / "images" / "heroes"
        hero_dir.mkdir(parents=True, exist_ok=True)
        hero_file = hero_dir / f"{slug}_hero.jpg"
        local_logo = str(BASE_DIR / logo_url.lstrip("/")) if logo_url else None
        generate_hero_banner(
            business_name=biz_data.get("business_name", "My Store"),
            category=biz_data.get("category", "Store"),
            tagline=biz_data.get("tagline"),
            logo_path=local_logo,
            output_path=hero_file,
        )
        biz_data["hero_image_url"] = f"/static/images/heroes/{slug}_hero.jpg"

        if hero_file.exists():
            with open(hero_file, "rb") as hf:
                await update.message.reply_photo(
                    photo=hf,
                    caption="🎨 *Custom AI Hero Banner Generated!* Crafted using your brand colors, logo & tagline.",
                    parse_mode="Markdown"
                )
    except Exception as e:
        logger.warning(f"Could not generate hero banner preview: {e}")

    # Initialize products and prompt for product #1
    biz_data["products"] = []
    await update.message.reply_text(
        "1️⃣2️⃣ *Key Services or Products*\n\n"
        "Now let's add your products one by one.\n\n"
        "📦 *Product #1*: What is the product / service name?\n"
        "(e.g. `Chicken Biryani` or `Oil Change`)",
        parse_mode="Markdown"
    )
    return ASK_PROD_NAME


async def skip_logo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    biz_data = context.user_data.get("biz", {})
    slug = slugify(biz_data.get("business_name", "shop"))

    try:
        logo_dir = BASE_DIR / "static" / "images" / "logos"
        logo_dir.mkdir(parents=True, exist_ok=True)
        logo_file = logo_dir / f"{slug}_logo.png"
        generate_brand_monogram(
            business_name=biz_data.get("business_name", "Shop"),
            category=biz_data.get("category", "Store"),
            output_path=logo_file,
        )
        biz_data["logo_url"] = f"/static/images/logos/{slug}_logo.png"

        hero_dir = BASE_DIR / "static" / "images" / "heroes"
        hero_dir.mkdir(parents=True, exist_ok=True)
        hero_file = hero_dir / f"{slug}_hero.jpg"
        generate_hero_banner(
            business_name=biz_data.get("business_name", "My Store"),
            category=biz_data.get("category", "Store"),
            tagline=biz_data.get("tagline"),
            logo_path=str(logo_file),
            output_path=hero_file,
        )
        biz_data["hero_image_url"] = f"/static/images/heroes/{slug}_hero.jpg"

        if hero_file.exists():
            with open(hero_file, "rb") as hf:
                await update.message.reply_photo(
                    photo=hf,
                    caption="✨ *Branded Monogram Logo & Custom Hero Banner Generated!*",
                    parse_mode="Markdown"
                )
    except Exception as e:
        logger.warning(f"Fallback monogram generation: {e}")

    biz_data["products"] = []
    await update.message.reply_text(
        "1️⃣2️⃣ *Key Services or Products*\n\n"
        "Now let's add your products one by one.\n\n"
        "📦 *Product #1*: What is the product / service name?\n"
        "(e.g. `Chicken Biryani` or `Oil Change`)",
        parse_mode="Markdown"
    )
    return ASK_PROD_NAME


async def ask_prod_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt.lower() in ["done", "/done", "finish", "finished", "no more", "stop", "exit"]:
        return await finish_products_wizard(update, context)

    context.user_data["current_prod"] = {
        "name": txt,
        "image_url": None,
        "price": 0.0,
    }

    await update.message.reply_text(
        f"📸 Please upload or send a **photo** for *{txt}*.\n\n"
        "*(Or send /skip if you don't have a photo right now)*",
        parse_mode="Markdown"
    )
    return ASK_PROD_PHOTO


async def ask_prod_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    curr = context.user_data.get("current_prod", {})
    prod_name = curr.get("name", "Product")

    # Check if user sent text instead of photo
    if update.message.text:
        txt = update.message.text.strip().lower()
        if txt in ["skip", "/skip", "no", "none", "na", "later"]:
            return await skip_prod_photo_handler(update, context)
        else:
            await update.message.reply_text(
                f"Please upload an image photo for *{prod_name}*, or send /skip to use the default photo.",
                parse_mode="Markdown"
            )
            return ASK_PROD_PHOTO

    # Handle image photo
    photo_file = None
    if update.message.photo:
        photo_file = update.message.photo[-1]
    elif update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("image/"):
        photo_file = update.message.document

    if photo_file:
        try:
            file_obj = await context.bot.get_file(photo_file.file_id)
            img_dir = BASE_DIR / "static" / "images" / "products"
            img_dir.mkdir(parents=True, exist_ok=True)
            filename = f"prod_{uuid.uuid4().hex[:8]}.jpg"
            dest_path = img_dir / filename
            await file_obj.download_to_drive(custom_path=str(dest_path))
            curr["image_url"] = f"/static/images/products/{filename}"
            await update.message.reply_text(f"📸 Photo saved for *{prod_name}*!")
        except Exception as e:
            logger.error(f"Failed to download product photo: {e}", exc_info=True)
            await update.message.reply_text("⚠️ Could not download photo, using default placeholder.")
    else:
        await update.message.reply_text(
            f"Please send a photo for *{prod_name}*, or type /skip.",
            parse_mode="Markdown"
        )
        return ASK_PROD_PHOTO

    await update.message.reply_text(
        f"💰 What is the **price** for *{prod_name}* in ₹?\n"
        f"(e.g. `250` or `180`)",
        parse_mode="Markdown"
    )
    return ASK_PROD_PRICE


async def skip_prod_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    curr = context.user_data.get("current_prod", {})
    prod_name = curr.get("name", "Product")
    curr["image_url"] = None
    await update.message.reply_text(
        f"Photo skipped for *{prod_name}*. (Default image will be used)\n\n"
        f"💰 What is the **price** for *{prod_name}* in ₹?\n"
        f"(e.g. `250` or `180`)",
        parse_mode="Markdown"
    )
    return ASK_PROD_PRICE


async def ask_prod_price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    digits = re.findall(r"\d+(?:\.\d+)?", txt)
    price = float(digits[0]) if digits else 0.0

    curr = context.user_data.get("current_prod", {})
    curr["price"] = price

    context.user_data["biz"]["products"].append(curr)
    prods = context.user_data["biz"]["products"]

    photo_status = "📸 Photo added" if curr.get("image_url") else "🖼️ Default photo"
    price_str = f"₹{int(price)}" if price.is_integer() else f"₹{price:.2f}"

    await update.message.reply_text(
        f"✅ *Added*: {curr['name']} — {price_str} ({photo_status})\n\n"
        f"📦 *Product #{len(prods) + 1}*: Enter next product / service name:\n"
        f"*(Or type `done` / send /done if you have finished adding products)*",
        parse_mode="Markdown"
    )
    return ASK_PROD_NAME


async def finish_products_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    biz_data = context.user_data.get("biz", {})
    products = biz_data.get("products", [])

    if not products:
        await update.message.reply_text(
            "⚠️ Please add at least 1 product or service before finishing.\n\n"
            "📦 *Product #1*: Enter product name (e.g. `Chicken Biryani`):",
            parse_mode="Markdown"
        )
        return ASK_PROD_NAME

    user_id = update.effective_user.id
    biz_data["owner_telegram_id"] = user_id

    # Propose change in changes table
    session = SessionLocal()
    try:
        change = Change(
            action=ChangeAction.CREATE_BUSINESS,
            business_id=None,
            product_id=None,
            old_value=None,
            new_value=biz_data,
            confirmed=False,
            reversed=False,
        )
        session.add(change)
        session.commit()
        session.refresh(change)

        # Build clean summary card
        card_lines = [
            f"🎉 *Summary for {biz_data.get('business_name')}*",
            f"• *Category*: {biz_data.get('category')}",
        ]
        if biz_data.get("tagline"):
            card_lines.append(f"• *Tagline*: \"{biz_data.get('tagline')}\"")
        if biz_data.get("phone"):
            card_lines.append(f"• *Phone*: {biz_data.get('phone')}")
        if biz_data.get("whatsapp"):
            card_lines.append(f"• *WhatsApp*: {biz_data.get('whatsapp')}")
        if biz_data.get("opening_hours"):
            card_lines.append(f"• *Hours*: {biz_data.get('opening_hours')}")
        if biz_data.get("trust_badges"):
            card_lines.append(f"• *Badges*: {biz_data.get('trust_badges')}")
        if biz_data.get("logo_url"):
            card_lines.append("• *Logo*: ✅ Configured")
        if biz_data.get("hero_image_url"):
            card_lines.append("• *Hero Section*: 🎨 AI Generated")

        card_lines.append("\n*Services / Products*:")
        for p in products:
            p_price = f"₹{int(p['price'])}" if float(p['price']).is_integer() else f"₹{p['price']:.2f}"
            icon = "📸" if p.get("image_url") else "🖼️"
            card_lines.append(f"  • {icon} {p['name']}: {p_price}")

        card_lines.append("\n*Ready to publish your website?*")

        keyboard = [
            [
                InlineKeyboardButton("✅ YES, Publish Website", callback_data=f"confirm:{change.change_id}"),
                InlineKeyboardButton("❌ NO, Cancel", callback_data=f"reject:{change.change_id}"),
            ]
        ]
        await update.message.reply_text(
            "\n".join(card_lines),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    finally:
        session.close()

    return ConversationHandler.END


async def cancel_wizard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels the step-by-step wizard."""
    await update.message.reply_text("❌ Setup cancelled. Send `/create` anytime to start again!", parse_mode="Markdown")
    return ConversationHandler.END


# =========================================================================
# Regular Commands & Natural Language Handlers
# =========================================================================

async def undo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /undo command."""
    session = SessionLocal()
    try:
        user_id = update.effective_user.id
        success, msg, web_path = undo_last_change(session, user_id)
        if success:
            full_url = f"{STORE_BASE_URL}{web_path}" if web_path else ""
            reply = f"✅ {msg}"
            if full_url:
                reply += f"\n🌐 Local URL: {full_url}"
            vercel_base = sync_vercel_deployment()
            if vercel_base and web_path:
                reply += f"\n☁️ Live Vercel: {vercel_base}{web_path}"
            await update.message.reply_text(reply)
        else:
            await update.message.reply_text(f"⚠️ {msg}")
    finally:
        session.close()


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Downloads voice note, transcribes via faster-whisper, and routes intent."""
    voice = update.message.voice
    if not voice:
        return

    status_msg = await update.message.reply_text("🎙️ Listening and transcribing your voice note...")

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tf:
        temp_audio_path = tf.name

    try:
        file_obj = await context.bot.get_file(voice.file_id)
        await file_obj.download_to_drive(custom_path=temp_audio_path)

        transcript = transcribe_audio(temp_audio_path)
        logger.info(f"Transcribed voice: {transcript}")

        await status_msg.edit_text(f'🎙️ Heard: "{transcript}"')
        await process_utterance(update, context, transcript)
    except Exception as e:
        logger.error(f"Error handling voice message: {e}", exc_info=True)
        await status_msg.edit_text(f"⚠️ Could not process voice note: {str(e)}")
    finally:
        if os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
            except Exception:
                pass


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles natural language text or captioned photo messages outside the wizard."""
    text = update.message.text or update.message.caption
    if not text:
        return

    photo_url = None
    if update.message.photo:
        try:
            photo_file = update.message.photo[-1]
            file_obj = await context.bot.get_file(photo_file.file_id)
            img_dir = BASE_DIR / "static" / "images" / "products"
            img_dir.mkdir(parents=True, exist_ok=True)
            filename = f"prod_{uuid.uuid4().hex[:8]}.jpg"
            dest_path = img_dir / filename
            await file_obj.download_to_drive(custom_path=str(dest_path))
            photo_url = f"/static/images/products/{filename}"
        except Exception as e:
            logger.warning(f"Could not save caption photo: {e}")

    await process_utterance(update, context, text, photo_url=photo_url)


async def process_utterance(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    photo_url: Optional[str] = None
):
    """
    Core pipeline:
    Intent Routing -> Confidence Gate -> State Machine Proposal / Execution
    """
    user_id = update.effective_user.id
    logger.info(f"Incoming message from user {user_id}: {text}")

    clean_lower = text.strip().lower()
    if clean_lower in ["hi", "hello", "hey", "start", "help", "namaste"]:
        welcome_text = (
            "Namaste! 🙏 Welcome to *DukaanMitra AI*.\n\n"
            "✨ *Two ways to create your website*:\n\n"
            "1️⃣ Send /create for an interactive step-by-step questionnaire.\n"
            "2️⃣ Or send your shop name & items in one message:\n"
            "`Paradise. Chicken Biryani 250, Chicken 65 180`\n\n"
            "Try either one right now! 🚀"
        )
        await update.message.reply_text(welcome_text, parse_mode="Markdown")
        return

    session = SessionLocal()

    try:
        # Route intent
        intent_result = route_intent(text)

        # Confidence Gate (< 0.7)
        is_confident, gate_error = handle_intent_confidence_gate(intent_result)
        if not is_confident:
            await update.message.reply_text(gate_error, parse_mode="Markdown")
            return

        # 1. UNDO_CHANGE
        if intent_result.intent == IntentType.UNDO_CHANGE:
            success, msg, web_path = undo_last_change(session, user_id)
            if success:
                full_url = f"{STORE_BASE_URL}{web_path}" if web_path else ""
                reply = msg
                if full_url:
                    reply += f"\n🌐 Local URL: {full_url}"
                vercel_base = sync_vercel_deployment()
                if vercel_base and web_path:
                    reply += f"\n☁️ Live Vercel: {vercel_base}{web_path}"
                await update.message.reply_text(reply)
            else:
                await update.message.reply_text(f"⚠️ {msg}")
            return

        # 2. SHOW_BUSINESS
        if intent_result.intent == IntentType.SHOW_BUSINESS:
            biz = find_business_by_owner(session, user_id)
            if not biz:
                await update.message.reply_text(
                    "You don't have a storefront yet! Send `/create` to set one up.",
                    parse_mode="Markdown"
                )
            else:
                full_url = f"{STORE_BASE_URL}/store/{biz.slug}"
                reply = f"🏪 *{biz.business_name}* is live!\n🌐 Local URL: {full_url}"
                if os.getenv("VERCEL_TOKEN"):
                    vercel_url = f"https://dukaanmitra-store-bcharishmareddy333-5668s-projects.vercel.app/store/{biz.slug}/"
                    reply += f"\n☁️ Live Vercel: {vercel_url}"
                await update.message.reply_text(
                    reply,
                    parse_mode="Markdown",
                )
            return

        # 3. MUTATING INTENTS (CREATE_BUSINESS, ADD_PRODUCT, UPDATE_PRICE)
        change, summary = propose_change(session, user_id, intent_result, image_url=photo_url)
        if not change:
            await update.message.reply_text(summary)
            return

        keyboard = [
            [
                InlineKeyboardButton("✅ YES, Publish", callback_data=f"confirm:{change.change_id}"),
                InlineKeyboardButton("❌ NO, Cancel", callback_data=f"reject:{change.change_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(summary, reply_markup=reply_markup, parse_mode="Markdown")

    finally:
        session.close()


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles inline button callbacks:
    confirm:{change_id} or reject:{change_id}
    """
    query = update.callback_query
    await query.answer()

    data = query.data
    session = SessionLocal()

    try:
        if data.startswith("confirm:"):
            change_id = int(data.split(":")[1])
            success, msg, web_path = confirm_change(session, change_id)
            if success:
                full_url = f"{STORE_BASE_URL}{web_path}" if web_path else ""
                reply = msg
                if full_url:
                    reply += f"\n🌐 Local URL: {full_url}"
                vercel_base = sync_vercel_deployment()
                if vercel_base and web_path:
                    reply += f"\n☁️ Live Vercel: {vercel_base}{web_path}"
                await query.edit_message_text(reply)
            else:
                await query.edit_message_text(f"⚠️ {msg}")

        elif data.startswith("reject:"):
            change_id = int(data.split(":")[1])
            cancel_msg = reject_change(session, change_id)
            await query.edit_message_text(f"❌ {cancel_msg}")

    except Exception as e:
        logger.error(f"Error handling callback query: {e}", exc_info=True)
        await query.edit_message_text("⚠️ An error occurred while processing your response.")
    finally:
        session.close()


def run_bot():
    """Starts the Telegram bot polling."""
    token = require_telegram_token()
    init_db()

    app = ApplicationBuilder().token(token).build()

    # Step-by-step Conversation Wizard
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("create", start_create_wizard)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name_handler)],
            ASK_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_type_handler)],
            ASK_TAGLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_tagline_handler)],
            ASK_ABOUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_about_handler)],
            ASK_TRUST: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_trust_handler)],
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone_handler)],
            ASK_WHATSAPP: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_whatsapp_handler)],
            ASK_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_address_handler)],
            ASK_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_hours_handler)],
            ASK_CTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_cta_handler)],
            ASK_LOGO: [
                CommandHandler("skip", skip_logo_handler),
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE | (filters.TEXT & ~filters.COMMAND),
                    ask_logo_handler,
                ),
            ],
            ASK_PROD_NAME: [
                CommandHandler("done", finish_products_wizard),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_prod_name_handler),
            ],
            ASK_PROD_PHOTO: [
                CommandHandler("skip", skip_prod_photo_handler),
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE | (filters.TEXT & ~filters.COMMAND),
                    ask_prod_photo_handler,
                ),
            ],
            ASK_PROD_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_prod_price_handler),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_wizard_handler)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("undo", undo_command))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle_text_message))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    logger.info("DukaanMitra AI Telegram Bot is polling...")
    app.run_polling()


if __name__ == "__main__":
    run_bot()
