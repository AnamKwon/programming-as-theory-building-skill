from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class ReservationStatus(str, Enum):
    ACTIVE = "active"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


# SQLAlchemy Models
class SKU(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    available_stock = Column(Integer, nullable=False, default=0)
    reserved_stock = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), nullable=False, default=ReservationStatus.ACTIVE)
    idempotency_key = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
    reservation_id = Column(String, nullable=True)
    idempotency_key = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)


# Pydantic Schemas
class SKUCreate(BaseModel):
    id: str
    name: str
    initial_stock: int = 0


class SKUResponse(BaseModel):
    id: str
    name: str
    available_stock: int
    reserved_stock: int
    created_at: datetime


class AdjustStockRequest(BaseModel):
    quantity: int = Field(..., description="Positive or negative quantity change")


class ReservationCreate(BaseModel):
    sku_id: str
    quantity: int
    idempotency_key: Optional[str] = None


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime
    confirmed_at: Optional[datetime]


class ReservationConfirmRequest(BaseModel):
    pass


class ReservationCancelRequest(BaseModel):
    pass


class OrderResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: OrderStatus
    reservation_id: Optional[str]
    idempotency_key: Optional[str]
    created_at: datetime
    confirmed_at: Optional[datetime]


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    offset: int
    limit: int


class ErrorResponse(BaseModel):
    detail: str
    code: str


def create_db_engine(database_url: str = "sqlite:///./commerce.db"):
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


def create_session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
