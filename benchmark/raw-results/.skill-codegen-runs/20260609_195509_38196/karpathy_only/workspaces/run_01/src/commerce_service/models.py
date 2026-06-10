"""Database and API models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()
DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, index=True)
    quantity_available = Column(Float, default=0)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, index=True)
    quantity = Column(Float)
    status = Column(String, default="pending", index=True)
    idempotency_key = Column(String, unique=True, index=True)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, index=True)
    quantity = Column(Float)
    status = Column(String, default="reserved", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SKUCreate(BaseModel):
    name: str
    quantity_available: float = Field(ge=0)


class SKUResponse(BaseModel):
    id: int
    name: str
    quantity_available: float

    class Config:
        from_attributes = True


class StockAdjustment(BaseModel):
    quantity_delta: float


class ReservationCreate(BaseModel):
    sku_id: int
    quantity: float = Field(gt=0)
    idempotency_key: str
    ttl_seconds: int = Field(default=300, ge=60)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: float
    status: Literal["pending", "confirmed", "cancelled"]
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    sku_id: int
    quantity: float
    status: Literal["reserved", "confirmed", "cancelled"]
    created_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    detail: str
    code: str


def init_db():
    Base.metadata.create_all(bind=engine)
