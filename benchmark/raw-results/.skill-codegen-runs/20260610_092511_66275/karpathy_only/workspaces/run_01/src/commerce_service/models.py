from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    stock = relationship("StockModel", back_populates="sku", uselist=False, cascade="all, delete-orphan")
    reservations = relationship("ReservationModel", back_populates="sku", cascade="all, delete-orphan")


class StockModel(Base):
    __tablename__ = "stock"

    sku_id = Column(String, ForeignKey("skus.id"), primary_key=True)
    quantity_available = Column(Integer, nullable=False, default=0)
    quantity_reserved = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    sku = relationship("SKUModel", back_populates="stock")


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending, confirmed, cancelled, expired
    idempotency_key = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    sku = relationship("SKUModel", back_populates="reservations")


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    status = Column(String, nullable=False, default="pending")  # pending, confirmed, failed
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


# Request/Response Pydantic Models

class CreateSKURequest(BaseModel):
    name: str
    price: float = Field(gt=0)


class SKUResponse(BaseModel):
    id: str
    name: str
    price: float
    created_at: datetime

    class Config:
        from_attributes = True


class StockAdjustmentRequest(BaseModel):
    sku_id: str
    quantity_change: int


class StockResponse(BaseModel):
    sku_id: str
    quantity_available: int
    quantity_reserved: int
    updated_at: datetime

    class Config:
        from_attributes = True


class CreateReservationRequest(BaseModel):
    sku_id: str
    quantity: int = Field(gt=0)
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
    message: str
