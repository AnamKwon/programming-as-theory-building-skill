from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

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


# SQLAlchemy ORM Models
class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True, index=True)
    sku_code = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String)
    stock_level = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, index=True, nullable=False)
    sku_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    idempotency_key = Column(String, unique=True, index=True, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True, index=True)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.RESERVED)
    total_items = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime)


# Pydantic Request/Response Models
class SKUCreate(BaseModel):
    sku_code: str
    name: str
    description: str | None = None
    stock_level: int = 0


class SKUResponse(BaseModel):
    id: int
    sku_code: str
    name: str
    description: str | None
    stock_level: int
    created_at: datetime

    class Config:
        from_attributes = True


class StockAdjustRequest(BaseModel):
    sku_id: int
    quantity_change: int = Field(..., description="Positive or negative integer")


class ReservationCreateRequest(BaseModel):
    order_id: str
    sku_id: int
    quantity: int = Field(..., gt=0)
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    order_id: str
    sku_id: int
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: str
    status: OrderStatus
    total_items: int
    created_at: datetime
    confirmed_at: datetime | None = None

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


# Configuration
def get_engine(database_url: str):
    return create_engine(
        database_url,
        connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
    )


def get_session_maker(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
