from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku_code = Column(String(255), unique=True, nullable=False, index=True)
    current_stock = Column(Integer, default=0, nullable=False)
    reserved_count = Column(Integer, default=0, nullable=False)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), default=ReservationStatus.PENDING, nullable=False)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=False)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), default=OrderStatus.PENDING, nullable=False)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class SKUCreate(BaseModel):
    sku_code: str = Field(..., min_length=1)
    initial_stock: int = Field(default=0, ge=0)


class SKUResponse(BaseModel):
    id: int
    sku_code: str
    current_stock: int
    reserved_count: int


class StockAdjustment(BaseModel):
    adjustment: int = Field(..., description="Positive to add, negative to remove")


class ReservationCreate(BaseModel):
    sku_id: int
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)
    ttl_seconds: int = Field(default=300, gt=0, description="Reservation lifetime in seconds")


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    idempotency_key: str
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: OrderStatus
    reservation_id: int | None
    created_at: datetime


class OrderListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    orders: list[OrderResponse]


def init_db(db_url: str = "sqlite:///./commerce.db") -> sessionmaker:
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
