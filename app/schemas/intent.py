from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field
from app.schemas.extraction import ExtractedProduct


class IntentType(str, Enum):
    CREATE_BUSINESS = "CREATE_BUSINESS"
    ADD_PRODUCT = "ADD_PRODUCT"
    UPDATE_PRICE = "UPDATE_PRICE"
    UNDO_CHANGE = "UNDO_CHANGE"
    SHOW_BUSINESS = "SHOW_BUSINESS"


class IntentResult(BaseModel):
    intent: IntentType = Field(description="One of the 5 allowed intents")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    
    # Specific payload fields depending on intent
    shop_name: Optional[str] = Field(default=None, description="Shop name if CREATE_BUSINESS")
    category: Literal["Restaurant"] = "Restaurant"
    products: list[ExtractedProduct] = Field(default_factory=list, description="Extracted products if CREATE_BUSINESS")
    
    product_name: Optional[str] = Field(default=None, description="Target product name if ADD_PRODUCT or UPDATE_PRICE")
    new_price: Optional[float] = Field(default=None, description="Price in INR if ADD_PRODUCT or UPDATE_PRICE")
    
    explanation: Optional[str] = Field(default=None, description="Brief explanation or reason for confidence score")
