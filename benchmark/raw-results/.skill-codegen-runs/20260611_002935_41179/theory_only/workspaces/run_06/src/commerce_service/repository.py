"""Data access layer."""

from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import create_engine, select, desc
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError

from .models import Base, SKU, Reservation, Order, IdempotencyLog


class Repository:
    """Data access layer for all database operations."""

    def __init__(self, database_url: str = "sqlite:///commerce.db"):
        self.engine = create_engine(database_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        """Create a new SKU."""
        session = self.get_session()
        try:
            db_sku = SKU(sku=sku, stock=initial_stock)
            session.add(db_sku)
            session.commit()
            session.refresh(db_sku)
            return db_sku
        finally:
            session.close()

    def get_sku_by_name(self, sku: str) -> Optional[SKU]:
        """Get SKU by name."""
        session = self.get_session()
        try:
            stmt = select(SKU).where(SKU.sku == sku)
            return session.execute(stmt).scalar_one_or_none()
        finally:
            session.close()

    def get_sku_by_id(self, sku_id: int) -> Optional[SKU]:
        """Get SKU by ID."""
        session = self.get_session()
        try:
            return session.get(SKU, sku_id)
        finally:
            session.close()

    def adjust_stock(self, sku: str, amount: int) -> int:
        """Adjust stock for a SKU and return new stock level."""
        session = self.get_session()
        try:
            stmt = select(SKU).where(SKU.sku == sku)
            db_sku = session.execute(stmt).scalar_one_or_none()
            if not db_sku:
                raise ValueError(f"SKU {sku} not found")
            db_sku.stock += amount
            session.commit()
            return db_sku.stock
        finally:
            session.close()

    def create_reservation(
        self, sku_id: int, sku: str, quantity: int, idempotency_key: str
    ) -> Reservation:
        """Create a new reservation."""
        session = self.get_session()
        try:
            reservation = Reservation(
                sku_id=sku_id,
                sku=sku,
                quantity=quantity,
                status="PENDING",
                idempotency_key=idempotency_key,
                created_at=datetime.utcnow(),
            )
            session.add(reservation)
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[Reservation]:
        """Get existing reservation by idempotency key."""
        session = self.get_session()
        try:
            stmt = select(Reservation).where(
                Reservation.idempotency_key == idempotency_key
            )
            return session.execute(stmt).scalar_one_or_none()
        finally:
            session.close()

    def get_reservation_by_id(self, reservation_id: int) -> Optional[Reservation]:
        """Get reservation by ID."""
        session = self.get_session()
        try:
            return session.get(Reservation, reservation_id)
        finally:
            session.close()

    def update_reservation_status(self, reservation_id: int, status: str) -> Reservation:
        """Update reservation status."""
        session = self.get_session()
        try:
            reservation = session.get(Reservation, reservation_id)
            if not reservation:
                raise ValueError(f"Reservation {reservation_id} not found")
            reservation.status = status
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def deduct_stock(self, sku_id: int, quantity: int) -> None:
        """Deduct stock from SKU."""
        session = self.get_session()
        try:
            db_sku = session.get(SKU, sku_id)
            if not db_sku:
                raise ValueError(f"SKU {sku_id} not found")
            db_sku.stock -= quantity
            session.commit()
        finally:
            session.close()

    def restore_stock(self, sku_id: int, quantity: int) -> None:
        """Restore stock to SKU."""
        session = self.get_session()
        try:
            db_sku = session.get(SKU, sku_id)
            if not db_sku:
                raise ValueError(f"SKU {sku_id} not found")
            db_sku.stock += quantity
            session.commit()
        finally:
            session.close()

    def create_order(self, reservation_id: int) -> Order:
        """Create a new order from a reservation."""
        session = self.get_session()
        try:
            order = Order(
                reservation_id=reservation_id,
                created_at=datetime.utcnow(),
            )
            session.add(order)
            session.commit()
            session.refresh(order)
            return order
        finally:
            session.close()

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> Tuple[list[Order], int]:
        """Get paginated orders."""
        session = self.get_session()
        try:
            stmt = select(Order).order_by(desc(Order.created_at))
            total = session.execute(select(lambda: 1).select_from(Order)).scalar() or 0

            stmt = stmt.offset((page - 1) * size).limit(size)
            orders = session.execute(stmt).scalars().all()

            stmt_count = select(lambda: None).select_from(Order)
            result = session.query(Order).count()

            return list(orders), result
        finally:
            session.close()

    def get_all_orders_count(self) -> int:
        """Get total count of orders."""
        session = self.get_session()
        try:
            result = session.query(Order).count()
            return result
        finally:
            session.close()
