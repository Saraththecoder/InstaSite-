import os
import re
from pathlib import Path
from typing import Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.db.database import SessionLocal
from app.db.models import Business, Product

TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_STORE_DIR = BASE_DIR / "static" / "store"

# Jinja2 environment with strict autoescape for HTML safety
jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"])
)


def slugify(text: str) -> str:
    """Generate clean URL-safe slug from shop name."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text or "shop"


def generate_storefront(business_id: int, session: Optional[Session] = None) -> tuple[str, str]:
    """
    Renders templates/restaurant.html and writes to static/store/{slug}/index.html.
    Idempotent and safe to call after every confirmed change or undo.
    Returns (slug, web_path).
    """
    own_session = False
    if session is None:
        session = SessionLocal()
        own_session = True

    try:
        business = session.query(Business).filter(Business.business_id == business_id).first()
        if not business:
            raise ValueError(f"Business not found for business_id={business_id}")

        products = (
            session.query(Product)
            .filter(Product.business_id == business_id)
            .order_by(Product.product_id.asc())
            .all()
        )

        slug = business.slug or slugify(business.business_name)

        # Ensure output directory exists
        store_dir = STATIC_STORE_DIR / slug
        store_dir.mkdir(parents=True, exist_ok=True)
        index_file = store_dir / "index.html"

        template = jinja_env.get_template("restaurant.html")
        rendered_html = template.render(
            business=business,
            products=products,
        )

        with open(index_file, "w", encoding="utf-8") as f:
            f.write(rendered_html)

        web_path = f"/store/{slug}"
        return slug, web_path
    finally:
        if own_session:
            session.close()
