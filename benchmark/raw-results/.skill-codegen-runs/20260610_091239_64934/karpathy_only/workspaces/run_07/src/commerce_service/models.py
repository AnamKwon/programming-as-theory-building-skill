from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()
engine = create_engine("sqlite:///commerce.db", echo=False)
SessionLocal = sessionmaker(bind=engine)


class SKUStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


# SQLAlchemy ORM Models
class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    code = Column(String(255), unique=True, nullable=False, index=True)
    quantity_available = Column(Integer, default=0, nullable=False)
    status = Column(String(50), default=SKUStatus.ACTIVE.value, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String(50), default=ReservationStatus.PENDING.value, nullable=False, index=True)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String(50), default=OrderStatus.PENDING.value, nullable=False, index=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


# Pydantic request/response models
class SKUCreate(BaseModel):
    code: str
    quantity_available: int


class SKUAdjustStock(BaseModel):
    adjustment: int = Field(..., description="Positive or negative adjustment to stock")


class SKUResponse(BaseModel):
    id: int
    code: str
    quantity_available: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReservationCreate(BaseModel):
    sku_id: int
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: str
    idempotency_key: str
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: str
    reservation_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedOrderResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int
    has_more: bool
