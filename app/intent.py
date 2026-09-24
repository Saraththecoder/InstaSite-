import re
import json
import logging
from typing import Optional
from app.config import GEMINI_API_KEY
from app.schemas.intent import IntentResult, IntentType
from app.extract import parse_spoken_number, extract_business_from_transcript, NUMBER_WORDS

logger = logging.getLogger(__name__)

INTENT_SYSTEM_PROMPT = """You are an intent classifier for DukaanMitra, a voice-first bot for restaurant owners.
Classify the user utterance into exactly ONE of the 5 allowed intents:
1. CREATE_BUSINESS: Creating/onboarding a new restaurant and dishes (e.g., "My shop is Sri Lakshmi Biryani. Chicken biryani 180, chicken 65 for 120").
2. ADD_PRODUCT: Adding a single new dish to the menu (e.g., "add mutton biryani for 250", "new item garlic naan 60").
3. UPDATE_PRICE: Updating the price of an existing dish (e.g., "change biryani price to 200", "make chicken biryani two hundred rupees", "biryani price should be 200 now").
4. UNDO_CHANGE: Reverting/undoing the last confirmed change (e.g., "undo", "revert last change", "cancel previous edit").
5. SHOW_BUSINESS: Viewing the restaurant menu, status, or storefront link (e.g., "show my business", "view storefront link", "what is my menu?").

Return strict JSON matching the IntentResult schema:
{
  "intent": "CREATE_BUSINESS" | "ADD_PRODUCT" | "UPDATE_PRICE" | "UNDO_CHANGE" | "SHOW_BUSINESS",
  "confidence": float (0.0 to 1.0),
  "shop_name": string or null,
  "category": "Restaurant",
  "products": [{"name": string, "price": float}],
  "product_name": string or null,
  "new_price": float or null,
  "explanation": string
}

IMPORTANT:
- If the user utterance is ambiguous, irrelevant, or not clearly one of these 5 intents, set confidence < 0.7.
- Spoken numbers like "two hundred" should be converted to numeric floats (200.0).
- "Chicken 65" is a dish name, not a price!
"""


def local_deterministic_intent_route(text: str) -> IntentResult:
    """
    Deterministic rule-based intent router for the 5 allowed intents.
    Enforces strict confidence scoring (returns < 0.7 if not clearly recognized).
    """
    clean_text = text.strip()
    lower_text = clean_text.lower()

    if not clean_text:
        return IntentResult(
            intent=IntentType.SHOW_BUSINESS,
            confidence=0.0,
            explanation="Empty input"
        )

    # 1. UNDO_CHANGE
    undo_patterns = [
        r"^/?undo\b",
        r"\brevert\s+(?:last|the last|previous|my)\s+(?:change|edit|update)?",
        r"\bcancel\s+(?:the\s+)?(?:last|previous)\s+(?:change|edit|update)?",
        r"^revert$",
        r"^go back$",
    ]
    for pattern in undo_patterns:
        if re.search(pattern, lower_text):
            return IntentResult(
                intent=IntentType.UNDO_CHANGE,
                confidence=0.95,
                explanation="Detected undo command"
            )

    # 2. SHOW_BUSINESS
    show_patterns = [
        r"\b(?:show|view|see|check|open|send|get)\s+(?:my\s+)?(?:business|store|storefront|shop|menu|link|website|page)\b",
        r"\bwhat\s+is\s+(?:my\s+)?(?:menu|storefront|website|shop)\b",
        r"^/?(?:menu|storefront|shop|website|link)$"
    ]
    for pattern in show_patterns:
        if re.search(pattern, lower_text):
            return IntentResult(
                intent=IntentType.SHOW_BUSINESS,
                confidence=0.95,
                explanation="Detected show business request"
            )

    # 3. UPDATE_PRICE
    # "change biryani price to 200", "make chicken biryani two hundred rupees", "biryani price should be 200 now", "update chicken 65 to 140"
    num_pattern = r"(?:\d+(?:\.\d+)?|one eighty|one twenty|two hundred|two fifty|three hundred|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)"
    update_patterns = [
        rf"(?:change|update|set|make|revise)\s+(?:the\s+)?(?:price\s+of\s+)?(.+?)(?:\s+price)?\s+(?:to|as|is|\=)\s+({num_pattern}|\d+)(?:\s+rupees|\s+rs|\s+now|$)",
        rf"(?:make|set)\s+(.+?)\s+(?:to\s+)?({num_pattern}|\d+)\s*(?:rupees|rs|inr|$)",
        rf"(.+?)\s+price\s+(?:should be|is now|to be|becomes)\s+({num_pattern}|\d+)(?:\s+rupees|\s+rs|\s+now|$)",
    ]
    for pattern in update_patterns:
        m = re.search(pattern, lower_text)
        if m:
            raw_prod = m.group(1).strip()
            raw_price = m.group(2).strip()

            # Clean words from raw_prod
            raw_prod = re.sub(r"^(?:the|price of|price)\s+", "", raw_prod).strip()
            raw_price = re.sub(r"^(?:rs\.?|rupees|inr)\s*", "", raw_price).strip()
            price_val = parse_spoken_number(raw_price)

            if price_val is not None and raw_prod and not raw_prod.startswith("add ") and len(raw_prod.split()) <= 4:
                prod_formatted = " ".join(w.capitalize() for w in raw_prod.split())
                return IntentResult(
                    intent=IntentType.UPDATE_PRICE,
                    confidence=0.95,
                    product_name=prod_formatted,
                    new_price=price_val,
                    explanation=f"Updating {prod_formatted} to {price_val}"
                )

    # 4. ADD_PRODUCT
    # "add mutton biryani for 250", "add paneer tikka 180", "new item garlic naan 60"
    add_match = re.search(
        r"(?:add|new item|include|insert)\s+(.+?)\s+(?:for|at|costs?|price|is)?\s*(?:rs\.?|rupees|inr)?\s*(\d+(?:\.\d+)?|one eighty|one twenty|two hundred|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|[a-z\s]+)\s*(?:rs\.?|rupees|inr)?$",
        lower_text
    )
    if add_match:
        p_name = add_match.group(1).strip()
        p_price_str = add_match.group(2).strip()
        # Protect "65" if in dish name
        price_val = parse_spoken_number(p_price_str)
        if price_val is not None and p_name and not ("change" in lower_text or "update" in lower_text):
            prod_formatted = " ".join(w.capitalize() for w in p_name.split())
            return IntentResult(
                intent=IntentType.ADD_PRODUCT,
                confidence=0.95,
                product_name=prod_formatted,
                new_price=price_val,
                explanation=f"Adding product {prod_formatted} at {price_val}"
            )

    # 5. CREATE_BUSINESS
    # e.g. "My shop is Sri Lakshmi Biryani. Chicken biryani 180, chicken 65 for 120"
    # or "Paradise. Biryani 250, Chicken 65 180"
    biz_triggers = ["my shop is", "my restaurant is", "welcome to", "create my restaurant", "start a new restaurant", "this is", "shop", "restaurant", "hotel", "cafe", "dhaba"]
    has_digit = bool(re.search(r"\d+", lower_text)) or any(w in lower_text for w in NUMBER_WORDS)
    is_create = any(t in lower_text for t in biz_triggers) or (has_digit and not lower_text.startswith("add ") and not any(u in lower_text for u in ["change ", "update ", "make ", "set "]))

    if is_create:
        extracted = extract_business_from_transcript(clean_text)
        if extracted.confidence >= 0.5 and extracted.products:
            return IntentResult(
                intent=IntentType.CREATE_BUSINESS,
                confidence=extracted.confidence,
                shop_name=extracted.shop_name,
                category="Restaurant",
                products=extracted.products,
                explanation=f"Create business {extracted.shop_name} with {len(extracted.products)} products"
            )

    # 6. Single shop name provided without dishes (e.g. "paradise", "Paradise Biryani")
    if not has_digit and len(clean_text.split()) <= 4 and clean_text.lower() not in ["hi", "hello", "hey", "help", "undo", "start"]:
        return IntentResult(
            intent=IntentType.SHOW_BUSINESS,
            confidence=0.5,
            shop_name=clean_text.title(),
            explanation=f"Only shop name '{clean_text}' provided without dishes or prices"
        )

    # If confidence is below 0.7 or unrecognized, return low confidence
    return IntentResult(
        intent=IntentType.SHOW_BUSINESS,
        confidence=0.3,
        explanation="Utterance could not be recognized with sufficient confidence"
    )


def route_intent(text: str) -> IntentResult:
    """
    Main intent routing entrypoint.
    Calls Gemini API with structured JSON output if GEMINI_API_KEY is present;
    otherwise falls back to deterministic router.
    Strictly guarantees Pydantic validated IntentResult.
    """
    if not text or not text.strip():
        return IntentResult(
            intent=IntentType.SHOW_BUSINESS,
            confidence=0.0,
            explanation="Empty utterance"
        )

    if GEMINI_API_KEY:
        try:
            from concurrent.futures import ThreadPoolExecutor
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=GEMINI_API_KEY)

            def _call_gemini_intent():
                return client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=f"{INTENT_SYSTEM_PROMPT}\n\nUser Utterance: {text}",
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=IntentResult,
                    ),
                )

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_call_gemini_intent)
                response = future.result(timeout=3.5)

            if response and response.text:
                data = json.loads(response.text)
                return IntentResult.model_validate(data)
        except Exception as e:
            logger.info(f"Gemini intent classification fallback ({e})")

    return local_deterministic_intent_route(text)


def handle_intent_confidence_gate(result: IntentResult) -> tuple[bool, str]:
    """
    Hard rule: If confidence < 0.7, caller must return a helpful clarification prompt
    rather than guessing.
    """
    if result.confidence < 0.7:
        if result.shop_name and result.shop_name.strip():
            return False, (
                f"I didn't quite catch that. Got your shop name: *{result.shop_name}*!\n\n"
                f"Now send your dishes with prices in one message or voice note. For example:\n"
                f"`{result.shop_name}. Chicken Biryani 250, Chicken 65 180`"
            )
        return False, "I didn't quite catch that. Please send your shop name with dishes and prices (e.g. 'Paradise. Chicken Biryani 250, Chicken 65 180') or a command like 'undo'."
    return True, ""
