"""Data access layer."""

from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Order, OrderStatus, Reservation, SKU, StockLevel


class RepositoryError(Exception):
    """Base repository error."""


class NotFoundError(RepositoryError):
    """Entity not found."""


class ConflictError(RepositoryError):
    """Conflict (e.g., duplicate idempotency key)."""


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # === SKU Operations ===

    def get_sku(self, sku_id: str) -> SKU | None:
        return self.session.execute(select(SKU).where(SKU.id == sku_id)).scalar_one_or_none()

    def create_sku(self, sku_id: str, name: str) -> SKU:
        sku = SKU(id=sku_id, name=name)
        self.session.add(sku)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            raise ConflictError(f"SKU {sku_id} already exists")
        return sku

    # === Stock Operations ===

    def get_stock(self, sku_id: str) -> StockLevel | None:
        return self.session.execute(select(StockLevel).where(StockLevel.sku_id == sku_id)).scalar_one_or_none()

    def initialize_stock(self, sku_id: str, quantity: int) -> StockLevel:
        """Create initial stock level for a SKU."""
        stock = StockLevel(sku_id=sku_id, available=quantity, reserved=0)
        self.session.add(stock)
        self.session.flush()
        return stock

    def adjust_stock(self, sku_id: str, quantity_delta: int) -> StockLevel:
        """Adjust available inventory (does not touch reserved)."""
        stock = self.get_stock(sku_id)
        if not stock:
            raise NotFoundError(f"No stock record for {sku_id}")
        stock.available += quantity_delta
        self.session.flush()
        return stock

    def reserve_stock(self, sku_id: str, quantity: int) -> None:
        """Move inventory from available to reserved."""
        stock = self.get_stock(sku_id)
        if not stock or stock.available < quantity:
            raise RepositoryError(f"Insufficient inventory for {sku_id}")
        stock.available -= quantity
        stock.reserved += quantity
        self.session.flush()

    def release_reserved_stock(self, sku_id: str, quantity: int) -> None:
        """Return reserved inventory to available."""
        stock = self.get_stock(sku_id)
        if not stock:
            raise NotFoundError(f"No stock record for {sku_id}")
        stock.reserved -= quantity
        stock.available += quantity
        self.session.flush()

    def confirm_reserved_stock(self, sku_id: str, quantity: int) -> None:
        """Remove reserved inventory (commit to order)."""
        stock = self.get_stock(sku_id)
        if not stock:
            raise NotFoundError(f"No stock record for {sku_id}")
        stock.reserved -= quantity
        self.session.flush()

    # === Reservation Operations ===

    def get_reservation(self, reservation_id: str) -> Reservation | None:
        return self.session.execute(
            select(Reservation).where(Reservation.id == reservation_id)
        ).scalar_one_or_none()

    def get_reservation_by_idempotency_key(self, key: str) -> Reservation | None:
        return self.session.execute(
            select(Reservation).where(Reservation.idempotency_key == key)
        ).scalar_one_or_none()

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: str | None = None,
    ) -> Reservation:
        """Create a new reservation."""
        reservation = Reservation(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status=OrderStatus.RESERVED.value,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.session.add(reservation)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            raise ConflictError("Idempotency key already used")
        return reservation

    def update_reservation_status(self, reservation_id: str, status: OrderStatus) -> Reservation:
        """Update reservation status."""
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise NotFoundError(f"Reservation {reservation_id} not found")
        reservation.status = status.value
        self.session.flush()
        return reservation

    # === Order Operations ===

    def get_order(self, order_id: str) -> Order | None:
        return self.session.execute(select(Order).where(Order.id == order_id)).scalar_one_or_none()

    def create_order(
        self,
        order_id: str,
        reservation_id: str,
        sku_id: str,
        quantity: int,
    ) -> Order:
        """Create a confirmed order from a reservation."""
        order = Order(
            id=order_id,
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status=OrderStatus.CONFIRMED.value,
        )
        self.session.add(order)
        self.session.flush()
        return order

    def list_orders(self, skip: int = 0, limit: int = 10) -> tuple[list[Order], int]:
        """List orders with pagination."""
        total = self.session.execute(select(Order)).scalars().all().__len__()
        orders = self.session.execute(
            select(Order).offset(skip).limit(limit)
        ).scalars().all()
        return orders, total

    def commit(self) -> None:
        """Commit the transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Rollback the transaction."""
        self.session.rollback()
