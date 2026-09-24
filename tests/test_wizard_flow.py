import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path

from app.db.models import Base, Business, Product, Change, ChangeAction
from app.state_machine import confirm_change, propose_change
from app.schemas.intent import IntentResult, IntentType
from app.generator import generate_storefront

TEST_ENGINE = create_engine("sqlite:///:memory:")
TestSession = sessionmaker(bind=TEST_ENGINE)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


def test_product_with_image_in_create_business():
    session = TestSession()
    try:
        biz_data = {
            "owner_telegram_id": 99999,
            "business_name": "Photo Test Bistro",
            "category": "Restaurant",
            "products": [
                {
                    "name": "Tandoori Chicken",
                    "price": 320.0,
                    "image_url": "/static/images/products/tandoori.jpg"
                },
                {
                    "name": "Butter Naan",
                    "price": 40.0,
                    "image_url": None
                }
            ]
        }

        change = Change(
            action=ChangeAction.CREATE_BUSINESS,
            new_value=biz_data,
            confirmed=False,
            reversed=False
        )
        session.add(change)
        session.commit()

        success, msg, web_path = confirm_change(session, change.change_id)
        assert success is True
        assert "photo-test-bistro" in web_path

        # Verify products in DB
        prods = session.query(Product).order_by(Product.product_id).all()
        assert len(prods) == 2

        assert prods[0].name == "Tandoori Chicken"
        assert prods[0].image_url == "/static/images/products/tandoori.jpg"
        assert prods[0].is_placeholder is False

        assert prods[1].name == "Butter Naan"
        assert prods[1].image_url is None
        assert prods[1].is_placeholder is True

        # Check generated HTML
        biz = session.query(Business).filter_by(slug="photo-test-bistro").first()
        slug, web_path = generate_storefront(biz.business_id, session)
        from app.generator import STATIC_STORE_DIR
        html_file = STATIC_STORE_DIR / slug / "index.html"
        content = html_file.read_text(encoding="utf-8")
        assert "/static/images/products/tandoori.jpg" in content
        assert "Tandoori Chicken" in content
        assert "Butter Naan" in content
    finally:
        session.close()


def test_add_product_with_image():
    session = TestSession()
    try:
        # Create business first
        biz = Business(
            owner_telegram_id=88888,
            business_name="Cafe Delight",
            category="Cafe",
            slug="cafe-delight"
        )
        session.add(biz)
        session.commit()

        # Propose ADD_PRODUCT with image_url
        intent = IntentResult(
            intent=IntentType.ADD_PRODUCT,
            product_name="Cold Coffee",
            new_price=120.0,
            confidence=0.95
        )
        change, summary = propose_change(
            session,
            owner_telegram_id=88888,
            intent_result=intent,
            image_url="/static/images/products/cold_coffee.jpg"
        )

        assert change is not None
        assert "(with photo)" in summary
        assert change.new_value.get("image_url") == "/static/images/products/cold_coffee.jpg"

        success, msg, web_path = confirm_change(session, change.change_id)
        assert success is True

        prod = session.query(Product).filter_by(name="Cold Coffee").first()
        assert prod is not None
        assert prod.image_url == "/static/images/products/cold_coffee.jpg"
        assert prod.is_placeholder is False
    finally:
        session.close()
