import uuid
from datetime import datetime, timedelta
from sqlalchemy import Column, String, Integer, DateTime, Enum
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class SKU(Base):
    __tablename__ = "skus"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Stock(Base):
    __tablename__ = "stocks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sku_id = Column(String(36), nullable=False, index=True)
    quantity = Column(Integer, default=0, nullable=False)
    reserved = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sku_id = Column(String(36), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    confirmed = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def is_expired(self):
        return datetime.utcnow() > self.expires_at

    def is_confirmed(self):
        return self.confirmed == 1


class Order(Base):
    __tablename__ = "orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reservation_id = Column(String(36), nullable=False, index=True)
    status = Column(String(20), default="PENDING", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
