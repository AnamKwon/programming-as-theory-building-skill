from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, create_engine, Float
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    code = Column(String(100), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(String(1000))
    stock_quantity = Column(Integer, default=0)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), default=ReservationStatus.PENDING)
    idempotency_key = Column(String(255), unique=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_ids = Column(String(1000))
    status = Column(String(20), default=OrderStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)


class CreateSKURequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    initial_stock: int = Field(default=0, ge=0)


class SKUResponse(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str]
    stock_quantity: int

    model_config = {"from_attributes": True}


class AdjustStockRequest(BaseModel):
    quantity_change: int = Field(..., description="Positive to add, negative to remove")


class CreateReservationRequest(BaseModel):
    sku_id: int
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = None


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderItemResponse(BaseModel):
    reservation_id: int
    sku_id: int
    quantity: int


class OrderResponse(BaseModel):
    id: int
    status: OrderStatus
    created_at: datetime
    items: list[OrderItemResponse]

    model_config = {"from_attributes": True}


class ListOrdersResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int


def get_engine(database_url: str = "sqlite:///./commerce.db"):
    return create_engine(database_url, connect_args={"check_same_thread": False})


def get_session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
