"""Business logic layer. Encodes domain rules and state machines."""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .models import SKU, Reservation, Order
from .repository import InventoryRepository, ReservationRepository, OrderRepository


RESERVATION_EXPIRATION_MINUTES = 15


class InventoryService:
    """Business rules for inventory management."""

    def __init__(self, session: Session):
        self.session = session
        self.inventory = InventoryRepository(session)
        self.reservation = ReservationRepository(session)
        self.order = OrderRepository(session)

    def create_sku(self, sku: str, quantity: int) -> SKU:
        """Create a new SKU with initial stock."""
        return self.inventory.create_sku(sku, quantity)

    def adjust_stock(self, sku: str, delta: int, reason: str) -> SKU:
        """Manual stock adjustment (audit-logged)."""
        self.inventory.adjust_stock(sku, delta, reason)
        return self.inventory.get_sku(sku)

    def reserve_inventory(self, sku: str, quantity: int, idempotency_key: str) -> Reservation:
        """Reserve inventory. Idempotency key prevents double-booking on retry.

        Raises ValueError if SKU not found or insufficient available stock.
        Returns idempotent: retrying with same key returns same reservation.
        """
        # Check idempotency: if we've seen this key, return existing reservation
        existing = self.reservation.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        # Check availability and deduct
        sku_record = self.inventory.get_sku(sku)
        if not sku_record:
            raise ValueError(f"SKU {sku} not found")
        if sku_record.available < quantity:
            raise ValueError(f"Insufficient available stock for {sku}: {sku_record.available} < {quantity}")

        # Deduct from available and create reservation
        self.inventory.deduct_available(sku, quantity)
        expires_at = datetime.utcnow() + timedelta(minutes=RESERVATION_EXPIRATION_MINUTES)
        reservation = self.reservation.create_reservation(sku, quantity, idempotency_key, expires_at)
        self.session.commit()
        return reservation

    def confirm_reservation(self, reservation_id: int) -> tuple[Reservation, Order]:
        """Confirm a pending reservation. Creates an order and moves stock to reserved.

        Raises ValueError if reservation not found, already confirmed, or expired.
        """
        reservation = self.reservation.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        if reservation.status != "pending":
            raise ValueError(f"Cannot confirm reservation with status {reservation.status}")
        if reservation.expires_at <= datetime.utcnow():
            raise ValueError(f"Reservation {reservation_id} has expired")

        # Move stock from deducted (held in available field) to reserved
        self.inventory.increment_reserved(reservation.sku, reservation.quantity)
        self.reservation.update_reservation_status(reservation_id, "confirmed", datetime.utcnow())
        order = self.order.create_order(reservation_id, reservation.sku, reservation.quantity)
        self.session.commit()

        return self.reservation.get_reservation(reservation_id), order

    def cancel_reservation(self, reservation_id: int) -> Reservation:
        """Cancel a pending or confirmed reservation. Restores available stock.

        Raises ValueError if reservation not found or already finalized.
        """
        reservation = self.reservation.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        if reservation.status in ("expired", "cancelled"):
            raise ValueError(f"Cannot cancel reservation with status {reservation.status}")

        if reservation.status == "pending":
            # Restore available stock
            self.inventory.restore_available(reservation.sku, reservation.quantity)
        elif reservation.status == "confirmed":
            # Move from reserved back to available
            self.inventory.decrement_reserved(reservation.sku, reservation.quantity)
            self.inventory.restore_available(reservation.sku, reservation.quantity)

        self.reservation.update_reservation_status(reservation_id, "cancelled")
        self.session.commit()
        return self.reservation.get_reservation(reservation_id)

    def expire_pending_reservations(self) -> int:
        """Mark all pending expired reservations as expired. Called periodically or on demand.

        Returns count of expired reservations.
        """
        now = datetime.utcnow()
        expired = self.reservation.list_pending_expired_reservations(now)
        for res in expired:
            self.inventory.restore_available(res.sku, res.quantity)
            self.reservation.update_reservation_status(res.id, "expired")
        if expired:
            self.session.commit()
        return len(expired)

    def get_order(self, order_id: int) -> Order | None:
        """Fetch order by ID."""
        return self.order.get_order(order_id)

    def list_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[Order], int]:
        """Paginated order list."""
        return self.order.list_orders(page, page_size)
