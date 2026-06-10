from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


# SQLAlchemy ORM Models
class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    base_price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<SKU {self.sku}>"


class StockModel(Base):
    __tablename__ = "stock"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Stock sku_id={self.sku_id} qty={self.quantity}>"


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default=ReservationStatus.PENDING)
    expires_at = Column(DateTime, nullable=False, index=True)
    idempotency_key = Column(String(255), unique=True, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Reservation {self.id} qty={self.quantity} status={self.status}>"


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, nullable=False, index=True)
    status = Column(String(20), nullable=False, default=OrderStatus.PENDING)
    quantity_reserved = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Order {self.id} status={self.status}>"


# Pydantic Request/Response Schemas
class CreateSKURequest(BaseModel):
    sku: str
    name: str
    base_price: float


class SKUResponse(BaseModel):
    id: int
    sku: str
    name: str
    base_price: float
    created_at: datetime


class AdjustStockRequest(BaseModel):
    quantity_delta: int = Field(description="Positive or negative adjustment")


class StockResponse(BaseModel):
    sku_id: int
    quantity: int


class CreateReservationRequest(BaseModel):
    sku_id: int
    quantity: int
    ttl_seconds: int = Field(default=3600, description="Reservation lifetime in seconds")
    idempotency_key: str | None = Field(default=None)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime


class ConfirmReservationRequest(BaseModel):
    idempotency_key: str | None = None


class CancelReservationRequest(BaseModel):
    idempotency_key: str | None = None


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    status: OrderStatus
    quantity_reserved: int
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    detail: str
