from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class SKU(Base):
    __tablename__ = "skus"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column()
    available: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    reserved: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    committed: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column()
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    state: Mapped[str] = mapped_column(String(20), default=ReservationState.PENDING)
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column()
    sku_id: Mapped[int] = mapped_column()
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    state: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# Pydantic schemas


class SKUCreate(BaseModel):
    sku_code: str
    name: str


class SKUResponse(BaseModel):
    id: int
    sku_code: str
    name: str


class StockAdjustment(BaseModel):
    adjustment: Decimal = Field(..., decimal_places=2)


class ReservationCreate(BaseModel):
    sku_id: int
    quantity: Decimal = Field(..., decimal_places=2, gt=0)
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: Decimal
    state: str
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku_id: int
    quantity: Decimal
    state: str
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    limit: int
    offset: int
