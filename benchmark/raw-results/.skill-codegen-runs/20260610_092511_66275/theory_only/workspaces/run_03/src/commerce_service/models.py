from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum as SQLEnum, Numeric
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel, Field

Base = declarative_base()


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderState(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"


# ORM Models
class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    code = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    available_stock = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_code = Column(String, ForeignKey("skus.code"), nullable=False)
    quantity = Column(Integer, nullable=False)
    state = Column(SQLEnum(ReservationState), default=ReservationState.PENDING, nullable=False)
    idempotency_key = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    state = Column(SQLEnum(OrderState), default=OrderState.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class OrderReservationModel(Base):
    __tablename__ = "order_reservations"

    id = Column(String, primary_key=True)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False)
    reservation_id = Column(String, ForeignKey("reservations.id"), nullable=False, unique=True)


# Pydantic Request/Response Models
class CreateSKURequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    initial_stock: int = Field(default=0, ge=0)


class AdjustStockRequest(BaseModel):
    quantity: int = Field(..., description="Positive or negative adjustment")


class CreateReservationRequest(BaseModel):
    sku_code: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: str
    sku_code: str
    quantity: int
    state: ReservationState
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    id: str
    state: OrderState
    reservation_ids: list[str]
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int


class SKUResponse(BaseModel):
    id: str
    code: str
    name: str
    available_stock: int
    created_at: datetime
