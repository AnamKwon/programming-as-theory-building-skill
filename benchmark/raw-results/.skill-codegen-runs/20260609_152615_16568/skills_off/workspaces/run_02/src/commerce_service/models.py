from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


# ORM Models
class SKU(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True)
    sku_id = Column(String, nullable=False, unique=True)
    available = Column(Integer, default=0, nullable=False)
    reserved = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING)
    idempotency_key = Column(String, unique=True, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    reservation_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)


# Pydantic Schemas

class SKUCreate(BaseModel):
    id: str = Field(..., min_length=1)
    name: str
    price: float = Field(..., gt=0)


class SKUResponse(BaseModel):
    id: str
    name: str
    price: float
    created_at: datetime

    model_config = {"from_attributes": True}


class InventoryResponse(BaseModel):
    sku_id: str
    available: int
    reserved: int

    model_config = {"from_attributes": True}


class AdjustStockRequest(BaseModel):
    sku_id: str
    quantity_change: int = Field(..., description="Positive or negative adjustment")


class ReservationRequest(BaseModel):
    sku_id: str
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = None


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: OrderStatus
    created_at: datetime
    confirmed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


def init_db(database_url: str = "sqlite:///./commerce.db"):
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal
