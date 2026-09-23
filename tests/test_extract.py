import pytest
from app.extract import extract_business_from_transcript
from app.schemas.extraction import ExtractedBusiness


def test_fixture_1_normal_case():
    transcript = "My shop is Royal Biryani House. Chicken Biryani 220, Mutton Biryani 350"
    result = extract_business_from_transcript(transcript)
    
    assert isinstance(result, ExtractedBusiness)
    assert result.category == "Restaurant"
    assert "Royal Biryani House" in result.shop_name
    assert len(result.products) == 2
    
    names = [p.name.lower() for p in result.products]
    prices = {p.name.lower(): p.price for p in result.products}
    
    assert any("chicken biryani" in n for n in names)
    assert any("mutton biryani" in n for n in names)
    for n, pr in prices.items():
        if "chicken biryani" in n:
            assert pr == 220.0
        elif "mutton biryani" in n:
            assert pr == 350.0
    assert result.confidence >= 0.7


def test_fixture_2_spoken_numbers():
    # Spoken numbers: "one eighty" -> 180, "one twenty" -> 120
    transcript = "Welcome to Cafe Spice, cold coffee one eighty and sandwich one twenty"
    result = extract_business_from_transcript(transcript)
    
    assert isinstance(result, ExtractedBusiness)
    assert "Cafe Spice" in result.shop_name
    assert len(result.products) == 2
    
    prices = {p.name.lower(): p.price for p in result.products}
    assert any(pr == 180.0 for pr in prices.values())
    assert any(pr == 120.0 for pr in prices.values())
    assert result.confidence >= 0.7


def test_fixture_3_dish_with_number_chicken_65():
    # "Chicken 65" contains 65 which is part of the dish name, not the price!
    transcript = "Sri Krishna Tiffins, Chicken 65 for 120 and Paneer 65 for 100"
    result = extract_business_from_transcript(transcript)
    
    assert isinstance(result, ExtractedBusiness)
    assert "Sri Krishna Tiffins" in result.shop_name
    assert len(result.products) == 2
    
    names = [p.name for p in result.products]
    assert any("65" in n for n in names)
    
    prices = {p.name.lower(): p.price for p in result.products}
    for n, pr in prices.items():
        if "chicken" in n:
            assert pr == 120.0
        elif "paneer" in n:
            assert pr == 100.0
    assert result.confidence >= 0.7


def test_fixture_4_missing_price():
    # "Veg Meals" is missing price, "Sambar Rice" has 80 -> should handle gracefully without crashing
    transcript = "This is Annapurna Mess, we serve Veg Meals, Sambar Rice 80"
    result = extract_business_from_transcript(transcript)
    
    assert isinstance(result, ExtractedBusiness)
    assert "Annapurna Mess" in result.shop_name
    # Should not crash and should extract the valid product with price
    assert any(p.price == 80.0 for p in result.products)
    assert result.confidence >= 0.5


def test_fixture_5_filler_words():
    # Filler words "um", "so basically"
    transcript = "Um, so basically, my shop is Chai Point, so basically masala chai is twenty rupees"
    result = extract_business_from_transcript(transcript)
    
    assert isinstance(result, ExtractedBusiness)
    assert "Chai Point" in result.shop_name
    assert not result.shop_name.lower().startswith("so basically")
    assert not result.shop_name.lower().startswith("um")
    assert len(result.products) >= 1
    assert any("masala chai" in p.name.lower() and p.price == 20.0 for p in result.products)
    assert result.confidence >= 0.7


def test_fixture_6_multiple_products_in_one_sentence():
    # Three products in one breath
    transcript = "Star Bakers, vanilla pastry for 60, chocolate brownie 90, puff 30"
    result = extract_business_from_transcript(transcript)
    
    assert isinstance(result, ExtractedBusiness)
    assert "Star Bakers" in result.shop_name
    assert len(result.products) == 3
    
    prices = sorted([p.price for p in result.products])
    assert prices == [30.0, 60.0, 90.0]
    assert result.confidence >= 0.7


def test_fixture_7_price_correction_mid_sentence():
    # Correction: "100, no wait, make it 120"
    transcript = "Sagar Fast Food, Veg Fried Rice is 100, no wait, make it 120, and noodles 110"
    result = extract_business_from_transcript(transcript)
    
    assert isinstance(result, ExtractedBusiness)
    assert "Sagar Fast Food" in result.shop_name
    
    prices = {p.name.lower(): p.price for p in result.products}
    for n, pr in prices.items():
        if "fried rice" in n:
            assert pr == 120.0  # Corrected price, not old 100
        elif "noodles" in n:
            assert pr == 110.0
    assert result.confidence >= 0.7


def test_fixture_8_no_extractable_business_data():
    # Unrelated chatter: should return confidence < 0.5 and not crash
    transcript = "Hello, what is the weather today in Hyderabad?"
    result = extract_business_from_transcript(transcript)
    
    assert isinstance(result, ExtractedBusiness)
    assert result.confidence < 0.5
    assert len(result.products) == 0
