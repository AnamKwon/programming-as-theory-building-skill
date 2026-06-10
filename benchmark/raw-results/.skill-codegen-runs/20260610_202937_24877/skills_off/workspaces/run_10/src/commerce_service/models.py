"""Database models and request/response schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class SKUModel(Base):
    """SKU database model."""

    __tablename__ = "skus"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True)
    available_stock = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReservationModel(Base):
    """Reservation database model."""

    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, index=True)
    quantity = Column(Integer)
    status = Column(String, default="PENDING")  # PENDING, CONFIRMED, CANCELLED, EXPIRED
    idempotency_key = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderModel(Base):
    """Order database model."""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(Integer, index=True)
    sku = Column(String, index=True)
    quantity = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)


class SKURequest(BaseModel):
    """Create SKU request."""

    sku: str
    initial_stock: int


class StockAdjustRequest(BaseModel):
    """Adjust stock request."""

    sku: str
    amount: int


class ReservationRequest(BaseModel):
    """Create reservation request."""

    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    """Reservation response."""

    id: int
    sku: str
    quantity: int
    status: str
    idempotency_key: str
    created_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    """Order response."""

    id: int
    reservation_id: int
    sku: str
    quantity: int
    created_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    """Order list response."""

    items: list[OrderResponse]
    page: int
    size: int
    total: int


class StockResponse(BaseModel):
    """Stock response."""

    sku: str
    available_stock: int


def init_db(database_url: str = "sqlite:///./test.db"):
    """Initialize database."""
    engine = create_engine(
        database_url, connect_args={"check_same_thread": False} if "sqlite" in database_url else {}
    )
    Base.metadata.create_all(bind=engine)
    return engine


def get_session_maker(engine):
    """Get SQLAlchemy session maker."""
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
