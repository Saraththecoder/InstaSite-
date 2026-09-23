from typing import Literal
from pydantic import BaseModel, Field


class ExtractedProduct(BaseModel):
    name: str = Field(description="Name of the dish or product")
    price: float = Field(description="Price of the dish or product in INR")


class ExtractedBusiness(BaseModel):
    shop_name: str = Field(description="Name of the restaurant or food shop")
    category: Literal["Restaurant"] = "Restaurant"
    products: list[ExtractedProduct] = Field(default_factory=list, description="List of dishes or products extracted")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0 of the extraction quality")
