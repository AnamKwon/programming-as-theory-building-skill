from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import String, Integer, DateTime, Enum as SQLEnum, create_engine
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"


# ─── Pydantic Models (API Request/Response) ─────────────────────────────────

class CreateSKURequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    name: str
    stock_level: int

    class Config:
        from_attributes = True


class StockAdjustmentRequest(BaseModel):
    adjustment: int = Field(..., ge=-999999, le=999999)


class CreateReservationRequest(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0, le=999999)
    idempotency_key: Optional[str] = Field(None, max_length=255)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    status: OrderStatus
    sku_id: int
    quantity: int
    created_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    skip: int
    limit: int


# ─── SQLAlchemy ORM Models ───────────────────────────────────────────────────

from sqlalchemy import Column, ForeignKey, func
from sqlalchemy.orm import relationship


class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    stock_level = Column(Integer, nullable=False, default=0)

    reservations = relationship("Reservation", back_populates="sku")
    orders = relationship("Order", back_populates="sku")


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), nullable=False, default=ReservationStatus.PENDING)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    idempotency_key = Column(String(255), unique=True, nullable=True, index=True)

    sku = relationship("SKU", back_populates="reservations")
    order = relationship("Order", uselist=False, back_populates="reservation")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False, index=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    reservation = relationship("Reservation", back_populates="order")
    sku = relationship("SKU", back_populates="orders")


def init_db(db_url: str = "sqlite:///./commerce.db") -> tuple[str, Session]:
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine, Session(bind=engine)
