import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.db.database import SessionLocal, init_db
from app.db.models import Business, Product, Change, ChangeAction
from app.generator import generate_storefront

def set_state(state_num: int):
    init_db()
    session = SessionLocal()
    owner_id = 777777
    try:
        # Get or create business
        biz = session.query(Business).filter(Business.slug == "sri-lakshmi-biryani").first()
        if not biz:
            biz = Business(
                owner_telegram_id=owner_id,
                business_name="Sri Lakshmi Biryani",
                category="Restaurant",
                slug="sri-lakshmi-biryani",
                phone="+91 98765 43210",
                address="Shop 4, Main Road, Hyderabad",
                opening_hours="11:00 AM – 11:00 PM"
            )
            session.add(biz)
            session.flush()

        products = {p.name: p for p in session.query(Product).filter(Product.business_id == biz.business_id).all()}
        
        # Ensure products exist
        if "Chicken Biryani" not in products:
            cb = Product(business_id=biz.business_id, name="Chicken Biryani", price=180.0, is_placeholder=True)
            session.add(cb)
            products["Chicken Biryani"] = cb
        if "Chicken 65" not in products:
            c65 = Product(business_id=biz.business_id, name="Chicken 65", price=120.0, is_placeholder=True)
            session.add(c65)
            products["Chicken 65"] = c65
        
        session.flush()

        if state_num == 1:
            products["Chicken Biryani"].price = 180.0
            products["Chicken 65"].price = 120.0
            print("State 1: Initial (Chicken Biryani ₹180, Chicken 65 ₹120)")
        elif state_num == 2:
            products["Chicken Biryani"].price = 200.0
            products["Chicken 65"].price = 120.0
            print("State 2: Updated (Chicken Biryani ₹200, Chicken 65 ₹120)")
        elif state_num == 3:
            products["Chicken Biryani"].price = 180.0
            products["Chicken 65"].price = 120.0
            print("State 3: Reverted/Undo (Chicken Biryani ₹180, Chicken 65 ₹120)")

        session.commit()
        generate_storefront(biz.business_id, session)
        print("Storefront regenerated successfully.")
    finally:
        session.close()

if __name__ == "__main__":
    s = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    set_state(s)
