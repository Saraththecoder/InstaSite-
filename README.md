# 🇮🇳 DukaanMitra AI — Voice-First Digital Storefront Bot

> A voice-first AI prototype designed for Indian small business owners (such as local restaurants and dhabas) to create and manage a digital storefront entirely through Telegram using voice notes and natural text.

Built with **FastAPI**, **python-telegram-bot (v20+)**, **faster-whisper (local STT)**, **Google Gemini 2.5 Flash**, **SQLAlchemy + SQLite**, **Pydantic v2**, and **Tailwind CSS**.

---

## ✨ Features (MVP Scope)

1. **Voice-First Onboarding**: Voice note → local Whisper STT → Gemini structured extraction (with Pydantic validation) → confirmation card → live static HTML storefront.
2. **5 Core Intents**:
   - `CREATE_BUSINESS`: Onboards new restaurant and initial menu items.
   - `ADD_PRODUCT`: Adds a dish with name and price.
   - `UPDATE_PRICE`: Updates dish price (e.g. *"change biryani price to 200"*).
   - `UNDO_CHANGE`: Single-level undo reverting the last confirmed change.
   - `SHOW_BUSINESS`: Returns the live storefront URL.
3. **Confirm-Before-Publish**: Every mutating change presents an inline **[ YES, Publish ]** / **[ ❌ NO, Cancel ]** keyboard. No DB mutation occurs without explicit confirmation.
4. **Single-Level Undo**: Automatically reverts the latest confirmed modification from the `changes` table and regenerates the static website.
5. **Static Storefront Generation**: Regenerates a fast, responsive, SEO-ready Tailwind CSS static page at `static/store/{slug}/index.html` after each confirmed change.

---

## 🏗️ Architecture & Data Model

```
businesses: business_id (PK), owner_telegram_id, business_name, category,
            phone, address, opening_hours, slug, created_at, updated_at

products:   product_id (PK), business_id (FK), name, price, image_url,
            is_placeholder (bool), created_at, updated_at

changes:    change_id (PK), business_id (FK), product_id (FK, nullable),
            action (CREATE_BUSINESS|ADD_PRODUCT|UPDATE_PRICE),
            old_value (JSON, nullable), new_value (JSON), confirmed (bool),
            reversed (bool), timestamp
```

---

## 🚀 Setup & Installation

### 1. Prerequisites
- Python 3.11+ (Python 3.13 supported)
- Virtual environment (recommended)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file in the project root (see `.env.example`):
```env
GEMINI_API_KEY=your_gemini_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
STORE_BASE_URL=http://localhost:8000
DATABASE_URL=sqlite:///./dukaan_mitra.db
WHISPER_MODEL_SIZE=small
PORT=8000
```

#### How to get API Keys:
1. **Gemini API Key**:
   - Visit [Google AI Studio](https://aistudio.google.com/).
   - Click "Get API key" and paste it as `GEMINI_API_KEY`.
2. **Telegram Bot Token**:
   - Open Telegram and search for [@BotFather](https://t.me/botfather).
   - Send `/newbot`, choose a display name and username.
   - Copy the bot API token and paste it as `TELEGRAM_BOT_TOKEN`.

---

## 🏃 Running the Application

### 1. Start the Storefront Web Server
```bash
python -m uvicorn app.server:app --port 8000 --reload
```
- Open `http://localhost:8000/` to see the storefront registry.
- View any generated store at `http://localhost:8000/store/{slug}` (e.g. `http://localhost:8000/store/sri-lakshmi-biryani`).

### 2. Start the Telegram Bot
```bash
python -m app.bot
```
- Open Telegram, find your bot, and send `/start`.

---

## 🧪 Testing Without a Real Phone (Automated Test Harness)

You do **not** need a physical smartphone or Telegram client to test the full end-to-end pipeline.

### Run Automated Unit Tests
```bash
# Run all unit tests (32 tests across Phase 1, 2, and 3)
python -m pytest -v

# Run Phase 1 Extraction Tests (8 hand-written transcript fixtures)
python -m pytest tests/test_extract.py -v

# Run Phase 2 Intent Routing Tests (5 intents with 3+ phrasings + confidence gate)
python -m pytest tests/test_intent.py -v

# Run Phase 3 State Machine Tests (Propose, Confirm, Reject, Undo cycles)
python -m pytest tests/test_state_machine.py -v
```

### Run the Complete 10-Step Demo Script
Execute the exact hackathon demo flow programmatically:
```bash
python run_demo.py
```

This verifies all 10 steps end-to-end:
```text
1. Owner voice: "My shop is Sri Lakshmi Biryani. Chicken biryani 180, chicken 65 for 120"
2. Bot: Confirmation card with shop + 2 products, YES/NO
3. Owner: YES
4. Bot: "Storefront created: /store/sri-lakshmi-biryani" -> verifies HTML (₹180, ₹120)
5. Owner text: "change biryani price to 200"
6. Bot: "Chicken Biryani: ₹180 → ₹200. Publish?" YES/NO
7. Owner: YES
8. Bot: "Updated." -> verifies HTML updated to ₹200
9. Owner: "undo"
10. Bot: "Reverted Chicken Biryani to ₹180." -> verifies HTML reverted to ₹180
```

---

## 🛡️ Non-Negotiable Engineering Rules Enforced

- **Strict Pydantic Validation**: All LLM and extraction responses are validated against Pydantic models before touching the database.
- **Confirm-Before-Publish Pattern**: All mutating operations create a pending change in the `changes` table; database mutations are committed only upon explicit user confirmation.
- **Confidence Gate (< 0.7)**: Any utterance with confidence below 0.7 prompts the user for clarification rather than guessing.
- **XSS Prevention**: Jinja2 HTML autoescaping is strictly enabled for all business names and products.
