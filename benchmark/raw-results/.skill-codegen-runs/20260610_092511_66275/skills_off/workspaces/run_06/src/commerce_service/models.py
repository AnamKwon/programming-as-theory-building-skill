import os
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, PositiveInt
from sqlalchemy import Column, DateTime, Enum as SQLEnum, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class SKU(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    created_at = Column(DateTime, server_default=func.now())


class Stock(Base):
    __tablename__ = "stock"

    sku_id = Column(String, primary_key=True, index=True)
    quantity = Column(Integer, default=0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True, index=True)
    sku_id = Column(String, index=True)
    quantity = Column(Integer)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING)
    idempotency_key = Column(String, unique=True, index=True)
    expires_at = Column(DateTime)
    order_id = Column(String, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True, index=True)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.RESERVED)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SKURequest(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    price: Decimal = Field(..., gt=0)


class SKUResponse(BaseModel):
    id: str
    name: str
    price: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class StockResponse(BaseModel):
    sku_id: str
    quantity: int
    updated_at: datetime

    class Config:
        from_attributes = True


class AdjustStockRequest(BaseModel):
    sku_id: str
    quantity: int


class CreateReservationRequest(BaseModel):
    sku_id: str
    quantity: PositiveInt
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    order_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: str
    status: OrderStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    limit: int
    offset: int
