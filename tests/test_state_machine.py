import os
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Business, Product, Change, ChangeAction
from app.schemas.intent import IntentResult, IntentType
from app.schemas.extraction import ExtractedProduct
from app.state_machine import propose_change, confirm_change, reject_change, undo_last_change
from app.generator import STATIC_STORE_DIR


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_propose_reject_noop_cycle(test_db):
    owner_id = 12345
    intent = IntentResult(
        intent=IntentType.CREATE_BUSINESS,
        confidence=0.9,
        shop_name="Test Dhaba",
        category="Restaurant",
        products=[ExtractedProduct(name="Dal Tadka", price=120.0)],
    )

    # 1. Propose
    change, summary = propose_change(test_db, owner_id, intent)
    assert change is not None
    assert change.confirmed is False
    assert change.reversed is False
    assert "Test Dhaba" in summary
    assert "Dal Tadka" in summary

    # Businesses and products should NOT exist yet in database
    assert test_db.query(Business).count() == 0
    assert test_db.query(Product).count() == 0

    # 2. Reject (NO)
    reject_msg = reject_change(test_db, change.change_id)
    assert "cancelled" in reject_msg.lower()

    # Still no businesses or products
    assert test_db.query(Business).count() == 0
    assert test_db.query(Product).count() == 0


def test_propose_confirm_apply_and_undo_cycle(test_db):
    owner_id = 99999
    
    # --- STEP 1: CREATE BUSINESS ---
    create_intent = IntentResult(
        intent=IntentType.CREATE_BUSINESS,
        confidence=0.95,
        shop_name="Sri Lakshmi Biryani",
        category="Restaurant",
        products=[
            ExtractedProduct(name="Chicken Biryani", price=180.0),
            ExtractedProduct(name="Chicken 65", price=120.0),
        ],
    )
    change1, _ = propose_change(test_db, owner_id, create_intent)
    assert change1.confirmed is False

    # Confirm YES
    success, msg, web_path = confirm_change(test_db, change1.change_id)
    assert success is True
    assert "/store/sri-lakshmi-biryani" in web_path

    # Verify DB
    biz = test_db.query(Business).filter(Business.owner_telegram_id == owner_id).first()
    assert biz is not None
    assert biz.business_name == "Sri Lakshmi Biryani"
    products = test_db.query(Product).filter(Product.business_id == biz.business_id).all()
    assert len(products) == 2

    # Verify HTML storefront file written to disk
    store_file = STATIC_STORE_DIR / "sri-lakshmi-biryani" / "index.html"
    assert store_file.exists()
    content = store_file.read_text(encoding="utf-8")
    assert "Sri Lakshmi Biryani" in content
    assert "Chicken Biryani" in content
    assert "₹180" in content
    assert "Chicken 65" in content
    assert "₹120" in content

    # --- STEP 2: UPDATE PRICE ---
    update_intent = IntentResult(
        intent=IntentType.UPDATE_PRICE,
        confidence=0.95,
        product_name="Biryani",
        new_price=200.0,
    )
    change2, summary2 = propose_change(test_db, owner_id, update_intent)
    assert change2 is not None
    assert change2.confirmed is False
    assert "Chicken Biryani: ₹180 → ₹200. Publish?" in summary2

    # Confirm YES
    success2, msg2, _ = confirm_change(test_db, change2.change_id)
    assert success2 is True
    assert msg2 == "Updated."

    # Verify DB and file updated to ₹200
    biryani = test_db.query(Product).filter(Product.name == "Chicken Biryani").first()
    assert biryani.price == 200.0
    content2 = store_file.read_text(encoding="utf-8")
    assert "₹200" in content2

    # --- STEP 3: UNDO CHANGE ---
    undo_success, undo_msg, _ = undo_last_change(test_db, owner_id)
    assert undo_success is True
    assert "Reverted Chicken Biryani to ₹180." in undo_msg

    # Verify DB and file reverted to ₹180
    test_db.refresh(biryani)
    assert biryani.price == 180.0
    content3 = store_file.read_text(encoding="utf-8")
    assert "₹180" in content3

    # Change record must be marked reversed
    test_db.refresh(change2)
    assert change2.reversed is True

    # --- STEP 4: SECOND UNDO ---
    # Should revert business creation or report no price change
    undo2_success, undo2_msg, _ = undo_last_change(test_db, owner_id)
    assert undo2_success is True
    assert "Reverted storefront creation" in undo2_msg

    # Subsequent undo fails gracefully
    undo3_success, undo3_msg, _ = undo_last_change(test_db, owner_id)
    assert undo3_success is False
    assert "No recent confirmed changes" in undo3_msg
