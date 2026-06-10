"""Database abstraction layer. Single source of truth for data access."""

from datetime import datetime
from sqlalchemy.orm import Session
from .models import SKU, Reservation, Order, StockAdjustment


class InventoryRepository:
    """Query and update SKU inventory. Maintains available + reserved = total invariant."""

    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku: str, quantity: int) -> SKU:
        """Create a new SKU with initial stock."""
        existing = self.session.query(SKU).filter(SKU.sku == sku).first()
        if existing:
            raise ValueError(f"SKU {sku} already exists")
        record = SKU(sku=sku, available=quantity, reserved=0)
        self.session.add(record)
        self.session.flush()
        return record

    def get_sku(self, sku: str) -> SKU | None:
        """Fetch SKU by identifier."""
        return self.session.query(SKU).filter(SKU.sku == sku).first()

    def deduct_available(self, sku: str, quantity: int) -> None:
        """Reduce available stock (called when reserving)."""
        record = self.get_sku(sku)
        if not record:
            raise ValueError(f"SKU {sku} not found")
        if record.available < quantity:
            raise ValueError(f"Insufficient available stock for {sku}")
        record.available -= quantity
        self.session.flush()

    def increment_reserved(self, sku: str, quantity: int) -> None:
        """Increase reserved stock (called when confirming a reservation)."""
        record = self.get_sku(sku)
        if not record:
            raise ValueError(f"SKU {sku} not found")
        record.reserved += quantity
        self.session.flush()

    def decrement_reserved(self, sku: str, quantity: int) -> None:
        """Reduce reserved stock (called when cancelling or expiring)."""
        record = self.get_sku(sku)
        if not record:
            raise ValueError(f"SKU {sku} not found")
        if record.reserved < quantity:
            raise ValueError(f"Cannot reduce reserved below 0 for {sku}")
        record.reserved -= quantity
        self.session.flush()

    def restore_available(self, sku: str, quantity: int) -> None:
        """Restore available stock (called when releasing a hold)."""
        record = self.get_sku(sku)
        if not record:
            raise ValueError(f"SKU {sku} not found")
        record.available += quantity
        self.session.flush()

    def adjust_stock(self, sku: str, delta: int, reason: str) -> None:
        """Manual stock adjustment (positive or negative)."""
        record = self.get_sku(sku)
        if not record:
            raise ValueError(f"SKU {sku} not found")
        new_available = record.available + delta
        if new_available < 0:
            raise ValueError(f"Stock adjustment would result in negative available for {sku}")
        record.available = new_available
        self.session.add(StockAdjustment(sku=sku, delta=delta, reason=reason))
        self.session.flush()


class ReservationRepository:
    """Manage temporary inventory holds."""

    def __init__(self, session: Session):
        self.session = session

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str, expires_at: datetime
    ) -> Reservation:
        """Create a new reservation."""
        existing = (
            self.session.query(Reservation)
            .filter(Reservation.idempotency_key == idempotency_key)
            .first()
        )
        if existing:
            return existing
        record = Reservation(
            sku=sku,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            status="pending",
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_reservation(self, reservation_id: int) -> Reservation | None:
        """Fetch reservation by ID."""
        return self.session.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, key: str) -> Reservation | None:
        """Fetch reservation by idempotency key."""
        return (
            self.session.query(Reservation)
            .filter(Reservation.idempotency_key == key)
            .first()
        )

    def update_reservation_status(
        self, reservation_id: int, status: str, confirmed_at: datetime | None = None
    ) -> Reservation:
        """Update reservation status."""
        record = self.get_reservation(reservation_id)
        if not record:
            raise ValueError(f"Reservation {reservation_id} not found")
        record.status = status
        if confirmed_at:
            record.confirmed_at = confirmed_at
        self.session.flush()
        return record

    def list_pending_expired_reservations(self, now: datetime) -> list[Reservation]:
        """Find all pending reservations that have expired."""
        return (
            self.session.query(Reservation)
            .filter(Reservation.status == "pending", Reservation.expires_at <= now)
            .all()
        )


class OrderRepository:
    """Manage confirmed orders."""

    def __init__(self, session: Session):
        self.session = session

    def create_order(self, reservation_id: int, sku: str, quantity: int) -> Order:
        """Create an order from a confirmed reservation."""
        record = Order(reservation_id=reservation_id, sku=sku, quantity=quantity, status="confirmed")
        self.session.add(record)
        self.session.flush()
        return record

    def get_order(self, order_id: int) -> Order | None:
        """Fetch order by ID."""
        return self.session.query(Order).filter(Order.id == order_id).first()

    def list_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[Order], int]:
        """Paginated order list."""
        total = self.session.query(Order).count()
        orders = (
            self.session.query(Order)
            .order_by(Order.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return orders, total

    def update_order_status(self, order_id: int, status: str) -> Order:
        """Update order status."""
        record = self.get_order(order_id)
        if not record:
            raise ValueError(f"Order {order_id} not found")
        record.status = status
        self.session.flush()
        return record
