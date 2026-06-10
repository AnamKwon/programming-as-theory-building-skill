from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class SKURow(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    code = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StockRow(Base):
    __tablename__ = "stock"

    sku_id = Column(String, primary_key=True)
    quantity = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReservationRow(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default="pending", nullable=False)
    idempotency_key = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class OrderRow(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    reservation_id = Column(String, nullable=False)
    status = Column(String, default="confirmed", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    CONFIRMED = "confirmed"


class CreateSKURequest(BaseModel):
    code: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)


class CreateSKUResponse(BaseModel):
    id: str
    code: str
    description: str
    created_at: datetime


class AdjustStockRequest(BaseModel):
    adjustment: int = Field(...)


class CreateReservationRequest(BaseModel):
    sku_id: str
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = None


class CreateReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime
    expires_at: datetime


class ConfirmReservationRequest(BaseModel):
    pass


class ConfirmReservationResponse(BaseModel):
    order_id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime


class CancelReservationRequest(BaseModel):
    pass


class ListOrdersResponse(BaseModel):
    items: list["OrderResponse"]
    total: int
    offset: int
    limit: int


class OrderResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime


def get_engine(db_url: str = "sqlite:///./commerce.db"):
    return create_engine(db_url, connect_args={"check_same_thread": False})


def get_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine):
    Base.metadata.create_all(engine)
