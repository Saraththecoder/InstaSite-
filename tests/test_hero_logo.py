import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from PIL import Image

from app.db.models import Base, Business, Change, ChangeAction
from app.state_machine import confirm_change
from app.generator import generate_storefront, STATIC_STORE_DIR
from app.hero_generator import generate_brand_monogram, generate_hero_banner, sample_logo_color

TEST_ENGINE = create_engine("sqlite:///:memory:")
TestSession = sessionmaker(bind=TEST_ENGINE)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


def test_logo_and_hero_banner_generation(tmp_path):
    logo_path = tmp_path / "test_brand_logo.png"
    hero_path = tmp_path / "test_brand_hero.jpg"

    # 1. Monogram logo generation
    res_logo = generate_brand_monogram(
        business_name="Royal Curry House",
        category="Restaurant",
        output_path=logo_path,
    )
    assert Path(res_logo).exists()
    with Image.open(res_logo) as img:
        assert img.size == (400, 400)

    # 2. Hero banner generation
    res_hero = generate_hero_banner(
        business_name="Royal Curry House",
        category="Restaurant",
        tagline="Flavors fit for royalty",
        logo_path=res_logo,
        output_path=hero_path,
    )
    assert Path(res_hero).exists()
    with Image.open(res_hero) as img:
        assert img.size == (1200, 500)
        assert img.format == "JPEG"


def test_business_creation_with_logo_and_hero_rendering(tmp_path):
    session = TestSession()
    try:
        # Pre-generate logo
        logo_path = Path("static/images/logos/royal_logo.png")
        generate_brand_monogram("Royal Biryani", "Restaurant", logo_path)

        biz_data = {
            "owner_telegram_id": 77777,
            "business_name": "Royal Biryani",
            "category": "Restaurant",
            "tagline": "Finest Biryani in Town",
            "logo_url": "/static/images/logos/royal_logo.png",
            "products": [
                {"name": "Special Mutton Biryani", "price": 380.0, "image_url": None}
            ]
        }

        change = Change(
            action=ChangeAction.CREATE_BUSINESS,
            new_value=biz_data,
            confirmed=False,
            reversed=False,
        )
        session.add(change)
        session.commit()

        success, msg, web_path = confirm_change(session, change.change_id)
        assert success is True

        biz = session.query(Business).filter_by(slug="royal-biryani").first()
        assert biz is not None
        assert biz.logo_url == "/static/images/logos/royal_logo.png"
        assert biz.hero_image_url is not None
        assert "royal-biryani_hero.jpg" in biz.hero_image_url

        # Verify static storefront rendering
        slug, _ = generate_storefront(biz.business_id, session)
        html_file = STATIC_STORE_DIR / slug / "index.html"
        assert html_file.exists()
        content = html_file.read_text(encoding="utf-8")

        # Must contain logo and hero banner image tag
        assert "/static/images/logos/royal_logo.png" in content
        assert biz.hero_image_url in content
        assert "Royal Biryani" in content
        assert "Finest Biryani in Town" in content
    finally:
        session.close()
