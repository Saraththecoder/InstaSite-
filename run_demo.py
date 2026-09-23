import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.db.database import SessionLocal, init_db
from app.db.models import Business, Product, Change
from app.intent import route_intent, handle_intent_confidence_gate
from app.schemas.intent import IntentType
from app.state_machine import propose_change, confirm_change, undo_last_change
from app.generator import STATIC_STORE_DIR


def run_full_demo():
    print("=" * 60)
    print("DUKAANMITRA AI — END-TO-END DEMO SCRIPT VERIFICATION")
    print("=" * 60)

    init_db()
    session = SessionLocal()
    owner_id = 888888  # Demo owner ID

    try:
        # Clean up any previous demo run data for isolation
        existing_biz = session.query(Business).filter(Business.owner_telegram_id == owner_id).all()
        for b in existing_biz:
            session.delete(b)
        session.commit()

        # -------------------------------------------------------------
        # Step 1: Owner sends voice note transcript
        # -------------------------------------------------------------
        voice_transcript = "My shop is Sri Lakshmi Biryani. Chicken biryani 180, chicken 65 for 120"
        print(f"\n[Step 1] Owner sends voice: \"{voice_transcript}\"")

        intent1 = route_intent(voice_transcript)
        confident, _ = handle_intent_confidence_gate(intent1)
        assert confident, "Voice utterance failed confidence gate!"
        assert intent1.intent == IntentType.CREATE_BUSINESS, f"Expected CREATE_BUSINESS, got {intent1.intent}"

        # -------------------------------------------------------------
        # Step 2: Bot sends confirmation card with extracted shop + products
        # -------------------------------------------------------------
        change1, card_summary = propose_change(session, owner_id, intent1)
        print(f"\n[Step 2] Bot displays Confirmation Card (YES/NO):\n{card_summary}")
        assert change1 is not None and not change1.confirmed
        assert "Sri Lakshmi Biryani" in card_summary
        assert "Chicken Biryani" in card_summary
        assert "Chicken 65" in card_summary

        # -------------------------------------------------------------
        # Step 3: Owner taps YES
        # -------------------------------------------------------------
        print("\n[Step 3] Owner taps: [ YES, Publish ]")
        success1, reply1, web_path1 = confirm_change(session, change1.change_id)
        assert success1, "Confirmation failed!"

        # -------------------------------------------------------------
        # Step 4: Bot confirms storefront created & verify static HTML
        # -------------------------------------------------------------
        print(f"\n[Step 4] Bot: \"{reply1}\"")
        assert "/store/sri-lakshmi-biryani" in reply1

        html_file = STATIC_STORE_DIR / "sri-lakshmi-biryani" / "index.html"
        assert html_file.exists(), f"Storefront file does not exist at {html_file}"
        html_content = html_file.read_text(encoding="utf-8")
        assert "Sri Lakshmi Biryani" in html_content
        assert "Chicken Biryani" in html_content
        assert "₹180" in html_content
        assert "Chicken 65" in html_content
        assert "₹120" in html_content
        print("  ✓ State 1 Verified: Static HTML has both products and correct initial prices (₹180, ₹120)")

        # -------------------------------------------------------------
        # Step 5: Owner sends text: "change biryani price to 200"
        # -------------------------------------------------------------
        text_update = "change biryani price to 200"
        print(f"\n[Step 5] Owner sends text: \"{text_update}\"")

        intent2 = route_intent(text_update)
        confident2, _ = handle_intent_confidence_gate(intent2)
        assert confident2, "Text update failed confidence gate!"
        assert intent2.intent == IntentType.UPDATE_PRICE, f"Expected UPDATE_PRICE, got {intent2.intent}"

        # -------------------------------------------------------------
        # Step 6: Bot: "Chicken Biryani: ₹180 → ₹200. Publish?" YES/NO
        # -------------------------------------------------------------
        change2, card_summary2 = propose_change(session, owner_id, intent2)
        print(f"\n[Step 6] Bot displays Confirmation Card (YES/NO):\n\"{card_summary2}\"")
        assert change2 is not None and not change2.confirmed
        assert "Chicken Biryani: ₹180 → ₹200. Publish?" in card_summary2

        # -------------------------------------------------------------
        # Step 7: Owner taps YES
        # -------------------------------------------------------------
        print("\n[Step 7] Owner taps: [ YES, Publish ]")
        success2, reply2, _ = confirm_change(session, change2.change_id)
        assert success2, "Price update confirmation failed!"

        # -------------------------------------------------------------
        # Step 8: Bot: "Updated." — reload storefront, verify ₹200
        # -------------------------------------------------------------
        print(f"\n[Step 8] Bot: \"{reply2}\"")
        assert reply2 == "Updated."

        html_content2 = html_file.read_text(encoding="utf-8")
        assert "₹200" in html_content2, "Price was not updated to ₹200 in static HTML!"
        print("  ✓ State 2 Verified: Static HTML reloaded, shows updated price ₹200")

        # -------------------------------------------------------------
        # Step 9: Owner sends text: "undo"
        # -------------------------------------------------------------
        undo_input = "undo"
        print(f"\n[Step 9] Owner sends text: \"{undo_input}\"")

        intent3 = route_intent(undo_input)
        assert intent3.intent == IntentType.UNDO_CHANGE, f"Expected UNDO_CHANGE, got {intent3.intent}"

        # -------------------------------------------------------------
        # Step 10: Bot: "Reverted Chicken Biryani to ₹180." — verify ₹180
        # -------------------------------------------------------------
        undo_success, undo_reply, _ = undo_last_change(session, owner_id)
        assert undo_success, "Undo failed!"
        print(f"\n[Step 10] Bot: \"{undo_reply}\"")
        assert "Reverted Chicken Biryani to ₹180." in undo_reply

        html_content3 = html_file.read_text(encoding="utf-8")
        assert "₹180" in html_content3, "Price was not reverted to ₹180 in static HTML!"
        print("  ✓ State 3 Verified: Static HTML reloaded, shows reverted price ₹180")

        print("\n" + "=" * 60)
        print("SUCCESS! ALL 10 DEMO SCRIPT STEPS PASSED PERFECTLY!")
        print("=" * 60)

    finally:
        session.close()


if __name__ == "__main__":
    run_full_demo()
