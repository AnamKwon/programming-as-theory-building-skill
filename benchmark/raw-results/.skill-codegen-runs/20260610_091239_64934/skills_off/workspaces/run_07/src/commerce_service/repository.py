"""Data access layer."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import OrderStatus, Reservation, SKU, Stock


class Repository:
    """Data access layer for database operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku_id: str, name: str) -> SKU:
        """Create a new SKU."""
        sku = SKU(id=sku_id, name=name)
        self.session.add(sku)
        self.session.flush()
        return sku

    def get_sku(self, sku_id: str) -> Optional[SKU]:
        """Get a SKU by ID."""
        return self.session.query(SKU).filter(SKU.id == sku_id).first()

    def get_stock(self, sku_id: str) -> Optional[Stock]:
        """Get stock for a SKU."""
        return self.session.query(Stock).filter(Stock.sku_id == sku_id).first()

    def update_stock(self, sku_id: str, delta: int) -> Stock:
        """Update stock quantity for a SKU."""
        stock = self.session.query(Stock).filter(Stock.sku_id == sku_id).first()
        if stock is None:
            stock = Stock(sku_id=sku_id, quantity=max(0, delta))
            self.session.add(stock)
        else:
            stock.quantity = max(0, stock.quantity + delta)
        self.session.flush()
        return stock

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at: datetime,
    ) -> Reservation:
        """Create a new reservation."""
        reservation = Reservation(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status=OrderStatus.RESERVED.value,
            expires_at=expires_at,
        )
        self.session.add(reservation)
        self.session.flush()
        return reservation

    def get_reservation(self, reservation_id: str) -> Optional[Reservation]:
        """Get a reservation by ID."""
        return (
            self.session.query(Reservation)
            .filter(Reservation.id == reservation_id)
            .first()
        )

    def confirm_reservation(self, reservation_id: str) -> Optional[Reservation]:
        """Confirm a reservation and update its status."""
        reservation = self.get_reservation(reservation_id)
        if reservation:
            reservation.status = OrderStatus.CONFIRMED.value
            reservation.confirmed_at = datetime.utcnow()
            self.session.flush()
        return reservation

    def cancel_reservation(self, reservation_id: str) -> Optional[Reservation]:
        """Cancel a reservation and update its status."""
        reservation = self.get_reservation(reservation_id)
        if reservation:
            reservation.status = OrderStatus.CANCELLED.value
            self.session.flush()
        return reservation

    def get_reservation_by_sku_and_status(
        self, sku_id: str, status: str
    ) -> list[Reservation]:
        """Get reservations for a SKU with a given status."""
        return (
            self.session.query(Reservation)
            .filter(Reservation.sku_id == sku_id, Reservation.status == status)
            .all()
        )

    def get_reservations(
        self, skip: int = 0, limit: int = 10
    ) -> tuple[list[Reservation], int]:
        """Get paginated reservations."""
        query = self.session.query(Reservation).order_by(Reservation.created_at.desc())
        total = query.count()
        items = query.offset(skip).limit(limit).all()
        return items, total

    def commit(self) -> None:
        """Commit the current transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self.session.rollback()
