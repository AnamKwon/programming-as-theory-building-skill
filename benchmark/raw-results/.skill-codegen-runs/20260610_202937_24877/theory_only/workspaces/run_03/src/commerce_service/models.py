from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class SKUOrm(Base):
    __tablename__ = "skus"

    sku = Column(String, primary_key=True)
    initial_stock = Column(Integer, nullable=False)
    available_stock = Column(Integer, nullable=False)


class ReservationOrm(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sku = Column(String, ForeignKey("skus.sku"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    idempotency_key = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class OrderOrm(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    status = Column(String, nullable=False, default="CONFIRMED")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int


class SKUResponse(BaseModel):
    sku: str
    initial_stock: int
    available_stock: int


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class StockAdjustmentResponse(BaseModel):
    sku: str
    available_stock: int


class CreateReservationRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    status: str
    created_at: datetime


class PaginatedOrdersResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    status: str


def get_database_url(db_path: str = "commerce.db") -> str:
    return f"sqlite:///{db_path}"


def get_engine(database_url: str):
    return create_engine(database_url, connect_args={"check_same_thread": False})


def get_session_factory(database_url: str):
    engine = get_engine(database_url)
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(database_url: str):
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
