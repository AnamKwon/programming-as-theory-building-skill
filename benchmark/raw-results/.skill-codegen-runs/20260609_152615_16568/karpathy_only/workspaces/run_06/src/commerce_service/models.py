from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"


# SQLAlchemy Models


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku_code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    stock_quantity = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    reservations = relationship(
        "ReservationItemModel", back_populates="sku", cascade="all, delete-orphan"
    )
    order_items = relationship(
        "OrderItemModel", back_populates="sku", cascade="all, delete-orphan"
    )


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, default=ReservationStatus.PENDING, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)

    items = relationship(
        "ReservationItemModel", back_populates="reservation", cascade="all, delete-orphan"
    )
    order = relationship("OrderModel", back_populates="reservation", uselist=False)


class ReservationItemModel(Base):
    __tablename__ = "reservation_items"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)

    reservation = relationship("ReservationModel", back_populates="items")
    sku = relationship("SKUModel", back_populates="reservations")


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    order_id = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, default=OrderStatus.PENDING, nullable=False)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    reservation = relationship("ReservationModel", back_populates="order")
    items = relationship(
        "OrderItemModel", back_populates="order", cascade="all, delete-orphan"
    )


class OrderItemModel(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)

    order = relationship("OrderModel", back_populates="items")
    sku = relationship("SKUModel", back_populates="order_items")


# Pydantic Request/Response Models


class CreateSKURequest(BaseModel):
    sku_code: str
    name: str
    initial_stock: int = 0


class AdjustStockRequest(BaseModel):
    quantity: int


class ReservationItemRequest(BaseModel):
    sku_id: int
    quantity: int


class CreateReservationRequest(BaseModel):
    idempotency_key: str
    items: list[ReservationItemRequest]
    expiry_minutes: int = 30


class ReservationItemResponse(BaseModel):
    sku_id: int
    quantity: int


class ReservationResponse(BaseModel):
    id: int
    reservation_id: str
    status: str
    items: list[ReservationItemResponse]
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class OrderItemResponse(BaseModel):
    sku_id: int
    quantity: int


class OrderResponse(BaseModel):
    id: int
    order_id: str
    status: str
    reservation_id: int
    items: list[OrderItemResponse]
    created_at: datetime

    class Config:
        from_attributes = True


class SKUResponse(BaseModel):
    id: int
    sku_code: str
    name: str
    stock_quantity: int
    created_at: datetime

    class Config:
        from_attributes = True
