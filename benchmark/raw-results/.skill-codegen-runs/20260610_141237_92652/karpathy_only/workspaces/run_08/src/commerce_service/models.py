from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from pydantic import BaseModel, Field

Base = declarative_base()

class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, nullable=False)
    available_stock = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    reservations = relationship("Reservation", back_populates="sku")

class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default="PENDING")
    idempotency_key = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    sku = relationship("SKU", back_populates="reservations")
    order = relationship("Order", uselist=False, back_populates="reservation")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    reservation = relationship("Reservation", back_populates="order")

class SKURequest(BaseModel):
    sku: str
    initial_stock: int

class SKUResponse(BaseModel):
    id: int
    sku: str
    available_stock: int

class StockAdjustRequest(BaseModel):
    sku: str
    amount: int

class StockAdjustResponse(BaseModel):
    sku: str
    available_stock: int

class ReservationRequest(BaseModel):
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
    created_at: datetime

class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int

class HealthResponse(BaseModel):
    status: str

def init_db(database_url: str = "sqlite:///commerce.db"):
    """Initialize database and return session factory."""
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return engine, SessionLocal
