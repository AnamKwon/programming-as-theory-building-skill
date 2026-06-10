"""Data access layer for all database operations."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import SKU, Reservation, Order


class Repository:
    """Repository for accessing and modifying data."""

    def __init__(self, session: Session):
        """Initialize repository with a database session."""
        self.session = session

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        """Create a new SKU with initial stock."""
        db_sku = SKU(sku=sku, stock=initial_stock)
        self.session.add(db_sku)
        self.session.commit()
        self.session.refresh(db_sku)
        return db_sku

    def get_sku_by_name(self, sku: str) -> Optional[SKU]:
        """Retrieve a SKU by its name."""
        return self.session.query(SKU).filter(SKU.sku == sku).first()

    def update_sku_stock(self, sku_id: int, amount: int) -> SKU:
        """Update stock level for a SKU."""
        sku = self.session.query(SKU).filter(SKU.id == sku_id).first()
        if sku:
            sku.stock += amount
            self.session.commit()
            self.session.refresh(sku)
        return sku

    def create_reservation(
        self, sku_id: int, sku: str, quantity: int, idempotency_key: str
    ) -> Reservation:
        """Create a new reservation."""
        reservation = Reservation(
            sku_id=sku_id,
            sku=sku,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status="PENDING",
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[Reservation]:
        """Retrieve a reservation by idempotency key."""
        return (
            self.session.query(Reservation)
            .filter(Reservation.idempotency_key == idempotency_key)
            .first()
        )

    def get_reservation_by_id(self, reservation_id: int) -> Optional[Reservation]:
        """Retrieve a reservation by ID."""
        return self.session.query(Reservation).filter(Reservation.id == reservation_id).first()

    def update_reservation_status(self, reservation_id: int, status: str) -> Optional[Reservation]:
        """Update the status of a reservation."""
        reservation = self.get_reservation_by_id(reservation_id)
        if reservation:
            reservation.status = status
            self.session.commit()
            self.session.refresh(reservation)
        return reservation

    def create_order(self, reservation_id: int) -> Order:
        """Create a new order from a reservation."""
        order = Order(reservation_id=reservation_id)
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_order_by_reservation_id(self, reservation_id: int) -> Optional[Order]:
        """Retrieve an order by reservation ID."""
        return self.session.query(Order).filter(Order.reservation_id == reservation_id).first()

    def list_orders(self, page: int = 1, size: int = 10) -> tuple[list[Order], int]:
        """List orders with pagination."""
        query = self.session.query(Order)
        total = query.count()
        offset = (page - 1) * size
        orders = query.offset(offset).limit(size).all()
        return orders, total
