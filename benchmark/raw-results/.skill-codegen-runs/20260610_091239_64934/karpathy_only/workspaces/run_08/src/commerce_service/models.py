from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Enum as SQLEnum, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class SKURecord(Base):
    __tablename__ = "skus"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReservationRecord(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(
        SQLEnum(ReservationStatus), default=ReservationStatus.PENDING
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OrderRecord(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sku: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SKUCreate(BaseModel):
    sku: str
    stock: int


class SKUResponse(BaseModel):
    id: int
    sku: str
    stock: int


class StockAdjustment(BaseModel):
    delta: int


class ReservationRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime


class ReservationConfirmRequest(BaseModel):
    reservation_id: int


class OrderResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    limit: int
    offset: int
