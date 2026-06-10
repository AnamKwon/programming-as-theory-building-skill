from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, Integer, String, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


# SQLAlchemy Models
class SKURecord(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    available_stock = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReservationRecord(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String)
    quantity = Column(Integer)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING)
    idempotency_key = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    confirmed_at = Column(DateTime, nullable=True)


class OrderRecord(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    sku_id = Column(String)
    quantity = Column(Integer)
    reservation_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


# Pydantic Schemas
class CreateSKURequest(BaseModel):
    sku_id: str
    initial_stock: int = 0


class CreateSKUResponse(BaseModel):
    sku_id: str
    available_stock: int


class AdjustStockRequest(BaseModel):
    adjustment: int


class AdjustStockResponse(BaseModel):
    sku_id: str
    available_stock: int


class CreateReservationRequest(BaseModel):
    sku_id: str
    quantity: int
    idempotency_key: Optional[str] = Field(default=None)


class CreateReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime


class ConfirmReservationResponse(BaseModel):
    order_id: str
    sku_id: str
    quantity: int
    created_at: datetime


class CancelReservationResponse(BaseModel):
    reservation_id: str
    status: ReservationStatus


class OrderResponse(BaseModel):
    order_id: str
    sku_id: str
    quantity: int
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int


class HealthResponse(BaseModel):
    status: str


def create_db_engine(db_url: str = None):
    import os
    if db_url is None:
        db_url = os.environ.get("DATABASE_URL", "sqlite:///commerce.db")

    if db_url.startswith("sqlite:///:memory:"):
        engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=None,
            echo=False,
        )
    else:
        engine = create_engine(db_url, echo=False)

    Base.metadata.create_all(engine)
    return engine
