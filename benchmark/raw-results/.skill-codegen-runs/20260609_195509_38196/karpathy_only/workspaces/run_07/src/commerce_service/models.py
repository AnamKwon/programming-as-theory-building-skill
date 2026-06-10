from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, create_engine, func
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
    CANCELLED = "cancelled"


# ORM Models
class SKU(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    current_stock = Column(Integer, default=0)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default=ReservationStatus.PENDING)
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=False, index=True)
    idempotency_key = Column(String, nullable=True, unique=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    reservation_id = Column(String, nullable=False, index=True)
    sku_id = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default=OrderStatus.PENDING)
    created_at = Column(DateTime, default=func.now())


# Pydantic Schemas
class SKUCreate(BaseModel):
    name: str = Field(..., min_length=1)
    current_stock: int = Field(default=0, ge=0)


class SKUResponse(BaseModel):
    id: str
    name: str
    current_stock: int


class StockAdjustment(BaseModel):
    quantity_delta: int = Field(..., description="Positive to add, negative to subtract")


class ReservationCreate(BaseModel):
    sku_id: str
    quantity: int = Field(..., gt=0)
    idempotency_key: str | None = None


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    id: str
    reservation_id: str
    sku_id: str
    quantity: int
    status: OrderStatus
    created_at: datetime


class PaginatedOrderResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    cursor: str | None = None


def init_db(database_url: str = "sqlite:///commerce.db"):
    if database_url.startswith("sqlite:///:memory:"):
        engine = create_engine(
            database_url, connect_args={"check_same_thread": False}, poolclass=None
        )
    else:
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
