"""Data access layer for persistence operations."""

from datetime import datetime

from sqlalchemy import and_
from sqlalchemy.orm import Session

from .models import Order, Reservation, ReservationStatus, SKU, Stock


class Repository:
    """Encapsulates all database operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku_id: str, name: str) -> SKU:
        """Create a new SKU."""
        sku = SKU(sku_id=sku_id, name=name)
        self.session.add(sku)
        self.session.flush()
        return sku

    def get_sku(self, sku_id: str) -> SKU | None:
        """Fetch a SKU by ID."""
        return self.session.query(SKU).filter(SKU.sku_id == sku_id).first()

    def get_or_create_stock(self, sku_id: str) -> Stock:
        """Get stock record or create if missing."""
        stock = self.session.query(Stock).filter(Stock.sku_id == sku_id).first()
        if not stock:
            stock = Stock(sku_id=sku_id, quantity=0, reserved=0)
            self.session.add(stock)
            self.session.flush()
        return stock

    def get_stock(self, sku_id: str) -> Stock | None:
        """Fetch stock by SKU ID."""
        return self.session.query(Stock).filter(Stock.sku_id == sku_id).first()

    def adjust_stock(self, sku_id: str, delta: int):
        """Adjust stock quantity (signed delta)."""
        stock = self.get_or_create_stock(sku_id)
        stock.quantity += delta
        stock.updated_at = datetime.utcnow()
        self.session.flush()

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> Reservation:
        """Create a new reservation."""
        reservation = Reservation(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )
        self.session.add(reservation)
        self.session.flush()
        return reservation

    def get_reservation(self, reservation_id: str) -> Reservation | None:
        """Fetch reservation by ID."""
        return self.session.query(Reservation).filter(Reservation.reservation_id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        """Fetch reservation by idempotency key for deduplication."""
        return self.session.query(Reservation).filter(Reservation.idempotency_key == idempotency_key).first()

    def update_reservation_status(self, reservation_id: str, status: ReservationStatus, confirmed_at: datetime | None = None):
        """Update reservation status."""
        reservation = self.get_reservation(reservation_id)
        if reservation:
            reservation.status = status
            if confirmed_at:
                reservation.confirmed_at = confirmed_at
            self.session.flush()

    def reserve_stock(self, sku_id: str, quantity: int):
        """Mark stock as reserved (for reservation creation)."""
        stock = self.get_or_create_stock(sku_id)
        stock.reserved += quantity
        stock.updated_at = datetime.utcnow()
        self.session.flush()

    def release_reserved_stock(self, sku_id: str, quantity: int):
        """Release reserved stock (for cancellation)."""
        stock = self.get_stock(sku_id)
        if stock:
            stock.reserved -= quantity
            stock.updated_at = datetime.utcnow()
            self.session.flush()

    def confirm_reserved_stock(self, sku_id: str, quantity: int):
        """Convert reserved stock to actual deduction (for confirmation)."""
        stock = self.get_stock(sku_id)
        if stock:
            stock.reserved -= quantity
            stock.quantity -= quantity
            stock.updated_at = datetime.utcnow()
            self.session.flush()

    def create_order(
        self,
        order_id: str,
        reservation_id: str,
        sku_id: str,
        quantity: int,
    ) -> Order:
        """Create order from confirmed reservation."""
        order = Order(
            order_id=order_id,
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
        )
        self.session.add(order)
        self.session.flush()
        return order

    def get_order(self, order_id: str) -> Order | None:
        """Fetch order by ID."""
        return self.session.query(Order).filter(Order.order_id == order_id).first()

    def get_orders_paginated(self, limit: int, offset: int) -> tuple[list[Order], int]:
        """Fetch orders with pagination."""
        total = self.session.query(Order).count()
        orders = self.session.query(Order).order_by(Order.created_at.desc()).limit(limit).offset(offset).all()
        return orders, total

    def cleanup_expired_reservations(self) -> int:
        """Mark expired reservations and release their stock. Returns count of expired."""
        now = datetime.utcnow()
        expired = self.session.query(Reservation).filter(
            and_(
                Reservation.expires_at <= now,
                Reservation.status == ReservationStatus.PENDING,
            )
        ).all()

        for res in expired:
            res.status = ReservationStatus.EXPIRED
            self.release_reserved_stock(res.sku_id, res.quantity)

        return len(expired)

    def commit(self):
        """Commit transaction."""
        self.session.commit()

    def rollback(self):
        """Rollback transaction."""
        self.session.rollback()
