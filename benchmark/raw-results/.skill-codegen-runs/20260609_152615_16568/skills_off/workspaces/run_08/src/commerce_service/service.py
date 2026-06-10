from datetime import datetime, timedelta

from .models import Order, Reservation, ReservationStatus, SKU
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class DuplicateReservationError(Exception):
    pass


class Service:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, code: str, name: str) -> SKU:
        sku = self.repo.create_sku(code, name)
        self.repo.initialize_stock(sku.id)
        return sku

    def adjust_stock(self, sku_id: int, quantity_delta: int) -> None:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        self.repo.adjust_stock(sku_id, quantity_delta)

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        reservation_ttl_seconds: int = 300,
    ) -> Reservation:
        # Check for duplicate idempotency key
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == ReservationStatus.CANCELLED:
                raise DuplicateReservationError(
                    f"Reservation with idempotency key {idempotency_key} was already cancelled"
                )
            return existing

        # Verify SKU exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        # Check stock availability
        if not self.repo.reserve_stock(sku_id, quantity):
            raise InsufficientStockError(f"Insufficient stock for SKU {sku_id}")

        # Create reservation
        expires_at = datetime.utcnow() + timedelta(seconds=reservation_ttl_seconds)
        reservation = self.repo.create_reservation(
            sku_id, quantity, idempotency_key, expires_at
        )
        return reservation

    def confirm_reservation(self, reservation_id: int) -> Order:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(f"Reservation is not pending: {reservation.status}")

        if reservation.expires_at <= datetime.utcnow():
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        # Update reservation status
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

        # Create order
        order = self.repo.create_order(
            reservation_id, reservation.sku_id, reservation.quantity
        )
        self.repo.update_order_status(order.id, reservation.status)
        return order

    def cancel_reservation(self, reservation_id: int) -> None:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CANCELLED:
            return

        if reservation.status == ReservationStatus.CONFIRMED:
            raise ValueError("Cannot cancel a confirmed reservation")

        # Release reserved stock
        self.repo.release_reserved_stock(reservation.sku_id, reservation.quantity)

        # Mark reservation as cancelled
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

    def expire_pending_reservations(self) -> int:
        """Clean up expired reservations and release their stock. Returns count expired."""
        now = datetime.utcnow()
        expired = self.repo.get_expired_reservations(now)

        for reservation in expired:
            self.repo.release_reserved_stock(reservation.sku_id, reservation.quantity)
            self.repo.update_reservation_status(
                reservation.id, ReservationStatus.CANCELLED
            )

        return len(expired)

    def get_orders(self, offset: int = 0, limit: int = 10) -> tuple[list[Order], int]:
        return self.repo.list_orders(offset, limit)
