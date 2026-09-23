import pytest
from app.intent import route_intent, handle_intent_confidence_gate
from app.schemas.intent import IntentType, IntentResult


# 1. CREATE_BUSINESS: 3+ phrasings
@pytest.mark.parametrize("phrase, expected_shop", [
    ("My shop is Sri Lakshmi Biryani. Chicken biryani 180, chicken 65 for 120", "Sri Lakshmi Biryani"),
    ("Create my restaurant Royal Biryani House with mutton biryani 350", "Royal Biryani House"),
    ("Start a new restaurant called Spice Hub with paneer butter masala 220", "Spice Hub"),
])
def test_intent_create_business(phrase, expected_shop):
    result = route_intent(phrase)
    assert isinstance(result, IntentResult)
    assert result.intent == IntentType.CREATE_BUSINESS
    assert result.confidence >= 0.7
    assert expected_shop in result.shop_name
    is_valid, _ = handle_intent_confidence_gate(result)
    assert is_valid is True


# 2. ADD_PRODUCT: 3+ phrasings
@pytest.mark.parametrize("phrase, expected_name, expected_price", [
    ("add mutton biryani for 250", "Mutton Biryani", 250.0),
    ("add paneer tikka 180", "Paneer Tikka", 180.0),
    ("new item garlic naan 60", "Garlic Naan", 60.0),
])
def test_intent_add_product(phrase, expected_name, expected_price):
    result = route_intent(phrase)
    assert isinstance(result, IntentResult)
    assert result.intent == IntentType.ADD_PRODUCT
    assert result.confidence >= 0.7
    assert expected_name.lower() in result.product_name.lower()
    assert result.new_price == expected_price
    is_valid, _ = handle_intent_confidence_gate(result)
    assert is_valid is True


# 3. UPDATE_PRICE: 3+ phrasings
@pytest.mark.parametrize("phrase, expected_product, expected_price", [
    ("change biryani price to 200", "Biryani", 200.0),
    ("make chicken biryani two hundred rupees", "Chicken Biryani", 200.0),
    ("biryani price should be 200 now", "Biryani", 200.0),
    ("update chicken 65 to 140", "Chicken 65", 140.0),
])
def test_intent_update_price(phrase, expected_product, expected_price):
    result = route_intent(phrase)
    assert isinstance(result, IntentResult)
    assert result.intent == IntentType.UPDATE_PRICE
    assert result.confidence >= 0.7
    assert expected_product.lower() in result.product_name.lower()
    assert result.new_price == expected_price
    is_valid, _ = handle_intent_confidence_gate(result)
    assert is_valid is True


# 4. UNDO_CHANGE: 3+ phrasings
@pytest.mark.parametrize("phrase", [
    "undo",
    "/undo",
    "revert last change",
    "cancel the last edit",
])
def test_intent_undo_change(phrase):
    result = route_intent(phrase)
    assert isinstance(result, IntentResult)
    assert result.intent == IntentType.UNDO_CHANGE
    assert result.confidence >= 0.7
    is_valid, _ = handle_intent_confidence_gate(result)
    assert is_valid is True


# 5. SHOW_BUSINESS: 3+ phrasings
@pytest.mark.parametrize("phrase", [
    "show my business",
    "view storefront link",
    "what is my menu?",
    "send my website link",
])
def test_intent_show_business(phrase):
    result = route_intent(phrase)
    assert isinstance(result, IntentResult)
    assert result.intent == IntentType.SHOW_BUSINESS
    assert result.confidence >= 0.7
    is_valid, _ = handle_intent_confidence_gate(result)
    assert is_valid is True


# Confidence threshold < 0.7 rule: "didn't understand, try again"
@pytest.mark.parametrize("ambiguous_phrase", [
    "what is the weather today in Hyderabad?",
    "tell me a joke about dogs",
    "aslkdfj qwperiu zxcv",
    "just random chatting here",
])
def test_intent_low_confidence_gate(ambiguous_phrase):
    result = route_intent(ambiguous_phrase)
    assert isinstance(result, IntentResult)
    assert result.confidence < 0.7
    is_valid, error_msg = handle_intent_confidence_gate(result)
    assert is_valid is False
    assert "didn't quite catch that" in error_msg
