from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field

Base = declarative_base()

RESERVATION_TTL_MINUTES = 30


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    inventories = relationship("InventoryModel", back_populates="sku", cascade="all, delete-orphan")


class InventoryModel(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True)
    sku_id = Column(String, ForeignKey("skus.id"), nullable=False, index=True)
    quantity = Column(Integer, default=0, nullable=False)
    reserved = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    sku = relationship("SKUModel", back_populates="inventories")


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, ForeignKey("skus.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending, confirmed, cancelled
    idempotency_key = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_sku_status", "sku_id", "status"),
    )

    def is_expired(self) -> bool:
        if self.status != "pending":
            return False
        age = datetime.utcnow() - self.created_at
        return age > timedelta(minutes=RESERVATION_TTL_MINUTES)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    reservation_id = Column(String, nullable=False, index=True)
    sku_id = Column(String, ForeignKey("skus.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False)  # pending, confirmed, completed, cancelled
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_sku_status", "sku_id", "status"),
    )


class SKUCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)


class SKUResponse(BaseModel):
    id: str
    name: str
    created_at: datetime

    class Config:
        from_attributes = True


class StockAdjustmentRequest(BaseModel):
    quantity: int = Field(..., description="Quantity to add (positive) or remove (negative)")


class ReservationCreate(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=100)


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime
    confirmed_at: datetime | None

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: str
    reservation_id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaginatedOrderResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    size: int
    pages: int
