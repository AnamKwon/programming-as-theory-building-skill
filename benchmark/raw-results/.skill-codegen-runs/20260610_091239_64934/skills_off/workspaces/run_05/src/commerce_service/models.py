from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.types import BigInteger, Integer

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class OrderStatus(str, Enum):
    RESERVED = "RESERVED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


# Pydantic schemas
class SKUCreate(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    sku: str
    name: str
    stock: int
    reserved: int


class StockAdjustmentRequest(BaseModel):
    quantity: int = Field(..., ge=-1000000, le=1000000)


class ReservationCreateRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationConfirmRequest(BaseModel):
    pass


class ReservationCancelRequest(BaseModel):
    pass


class ReservationResponse(BaseModel):
    reservation_id: int
    sku: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    order_id: int
    sku: str
    quantity: int
    status: OrderStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    offset: int
    limit: int


class HealthResponse(BaseModel):
    status: str = "healthy"


# SQLAlchemy ORM models
from sqlalchemy import Column, ForeignKey, UniqueConstraint

from sqlalchemy.orm import relationship


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    stock = Column(Integer, nullable=False, default=0)

    reservations = relationship("ReservationModel", back_populates="sku_obj")

    def available_stock(self) -> int:
        reserved = sum(
            r.quantity
            for r in self.reservations
            if r.status in (ReservationStatus.PENDING, ReservationStatus.CONFIRMED)
        )
        return self.stock - reserved


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    sku_code = Column(String(50), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default=ReservationStatus.PENDING)
    idempotency_key = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)

    sku_obj = relationship("SKUModel", back_populates="reservations")

    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_idempotency_key"),)

    def is_expired(self) -> bool:
        return (
            self.status == ReservationStatus.PENDING
            and datetime.utcnow() > self.expires_at
        )


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    sku = Column(String(50), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default=OrderStatus.RESERVED)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


def get_engine(database_url: str = "sqlite:///./commerce.db"):
    return create_engine(
        database_url, connect_args={"check_same_thread": False} if "sqlite" in database_url else {}
    )


def get_session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(engine):
    Base.metadata.create_all(bind=engine)
