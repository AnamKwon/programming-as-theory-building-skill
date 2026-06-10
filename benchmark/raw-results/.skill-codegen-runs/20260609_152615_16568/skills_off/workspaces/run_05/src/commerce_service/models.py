from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLEnum, create_engine
from sqlalchemy.orm import declarative_base
from typing import Optional

Base = declarative_base()


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class SKUModel(Base):
    __tablename__ = "skus"

    sku = Column(String, primary_key=True)
    available_quantity = Column(Integer, default=0, nullable=False)
    reserved_quantity = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReservationModel(Base):
    __tablename__ = "reservations"

    reservation_id = Column(String, primary_key=True)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    state = Column(SQLEnum(ReservationState), default=ReservationState.PENDING, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)


# Request/Response Schemas

class CreateSKURequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    initial_quantity: int = Field(default=0, ge=0)


class CreateSKUResponse(BaseModel):
    sku: str
    available_quantity: int
    reserved_quantity: int


class AdjustStockRequest(BaseModel):
    adjustment: int = Field(..., description="Positive to add, negative to subtract")


class AdjustStockResponse(BaseModel):
    sku: str
    available_quantity: int
    reserved_quantity: int


class CreateReservationRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = Field(None, max_length=255)


class CreateReservationResponse(BaseModel):
    reservation_id: str
    sku: str
    quantity: int
    state: ReservationState
    expires_at: datetime


class ConfirmReservationResponse(BaseModel):
    reservation_id: str
    sku: str
    quantity: int
    state: ReservationState
    confirmed_at: datetime


class CancelReservationResponse(BaseModel):
    reservation_id: str
    state: ReservationState


class OrderResponse(BaseModel):
    reservation_id: str
    sku: str
    quantity: int
    state: ReservationState
    created_at: datetime
    confirmed_at: Optional[datetime]


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    offset: int
    limit: int


def get_database_url(path: str = "commerce.db") -> str:
    return f"sqlite:///{path}"
