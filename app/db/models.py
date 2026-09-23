import enum
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Enum as SQLEnum,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ChangeAction(str, enum.Enum):
    CREATE_BUSINESS = "CREATE_BUSINESS"
    ADD_PRODUCT = "ADD_PRODUCT"
    UPDATE_PRICE = "UPDATE_PRICE"


class Business(Base):
    __tablename__ = "businesses"

    business_id = Column(Integer, primary_key=True, autoincrement=True)
    owner_telegram_id = Column(BigInteger, nullable=False, index=True)
    business_name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False, default="Shop / Retail Store")
    tagline = Column(String(500), nullable=True)
    about_us = Column(String(2000), nullable=True)
    trust_badges = Column(String(1000), nullable=True)
    phone = Column(String(50), nullable=True)
    whatsapp = Column(String(50), nullable=True)
    address = Column(String(500), nullable=True)
    opening_hours = Column(String(200), nullable=True)
    cta_text = Column(String(100), nullable=True, default="Book Now")
    slug = Column(String(255), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    products = relationship("Product", back_populates="business", cascade="all, delete-orphan")
    changes = relationship("Change", back_populates="business", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"

    product_id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(Integer, ForeignKey("businesses.business_id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    price = Column(Float, nullable=False)
    image_url = Column(String(500), nullable=True)
    is_placeholder = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    business = relationship("Business", back_populates="products")
    changes = relationship("Change", back_populates="product")


class Change(Base):
    __tablename__ = "changes"

    change_id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(Integer, ForeignKey("businesses.business_id"), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.product_id"), nullable=True, index=True)
    action = Column(SQLEnum(ChangeAction), nullable=False)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=False)
    confirmed = Column(Boolean, default=False, nullable=False)
    reversed = Column(Boolean, default=False, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    business = relationship("Business", back_populates="changes")
    product = relationship("Product", back_populates="changes")
