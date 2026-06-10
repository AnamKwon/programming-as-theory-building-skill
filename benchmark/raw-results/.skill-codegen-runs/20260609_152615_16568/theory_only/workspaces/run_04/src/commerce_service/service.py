import uuid
from datetime import datetime, timedelta
from typing import Optional

from .models import Reservation, ReservationStatus, SKU
from .repository import Repository


class ServiceError(Exception):
    pass


class ServiceValidationError(ServiceError):
    pass


class InsufficientStockError(ServiceError):
    pass


class ReservationNotFoundError(ServiceError):
    pass


class ReservationExpiredError(ServiceError):
    pass


class ReservationAlreadyConfirmedError(ServiceError):
    pass


class Service:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku: str, stock: int) -> SKU:
        if stock <= 0:
            raise ServiceValidationError("Stock must be positive")
        existing = self.repo.get_sku_by_name(sku)
        if existing:
            raise ServiceValidationError(f"SKU {sku} already exists")
        return self.repo.create_sku(sku, stock)

    def adjust_stock(self, sku_id: int, delta: int) -> SKU:
        sku = self.repo.get_sku_by_id(sku_id)
        if not sku:
            raise ServiceValidationError(f"SKU {sku_id} not found")
        new_stock = sku.stock + delta
        if new_stock < 0:
            raise ServiceValidationError(f"Stock cannot be negative")
        return self.repo.adjust_stock(sku_id, delta)

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str
    ) -> Reservation:
        if quantity <= 0:
            raise ServiceValidationError("Quantity must be positive")

        sku = self.repo.get_sku_by_id(sku_id)
        if not sku:
            raise ServiceValidationError(f"SKU {sku_id} not found")

        # Idempotency: return existing reservation if same key exists
        existing = self.repo.find_existing_reservation(sku_id, idempotency_key)
        if existing:
            if self._is_expired(existing):
                # Expired reservation should not be returned, release stock
                self._release_reservation(existing)
                # Fall through to create new one
            else:
                return existing

        # Stock availability check
        if sku.available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock: need {quantity}, available {sku.available}"
            )

        # Create reservation with TTL
        order_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)
        reservation = self.repo.create_reservation(
            order_id=order_id,
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )

        # Allocate stock
        self.repo.increment_reserved_stock(sku_id, quantity)
        return reservation

    def confirm_reservation(self, reservation_id: int) -> Reservation:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CONFIRMED:
            raise ReservationAlreadyConfirmedError(
                f"Reservation {reservation_id} already confirmed"
            )

        if reservation.status != ReservationStatus.PENDING:
            raise ServiceValidationError(
                f"Cannot confirm reservation with status {reservation.status}"
            )

        if self._is_expired(reservation):
            self._release_reservation(reservation)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        # Transition to confirmed, decrease available (already reserved)
        return self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED, confirmed_at=datetime.utcnow()
        )

    def cancel_reservation(self, reservation_id: int) -> Reservation:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CONFIRMED:
            raise ServiceValidationError(
                "Cannot cancel a confirmed reservation (order is immutable)"
            )

        if reservation.status in [ReservationStatus.CANCELLED, ReservationStatus.EXPIRED]:
            # Already released, idempotent
            return reservation

        # Release stock and mark as cancelled
        if reservation.status == ReservationStatus.PENDING:
            self.repo.decrement_reserved_stock(reservation.sku_id, reservation.quantity)
        return self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

    def get_order(self, order_id: str) -> Optional[Reservation]:
        return self.repo.get_reservation_by_order_id(order_id)

    def list_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[Reservation], int]:
        if page < 1:
            raise ServiceValidationError("Page must be >= 1")
        if page_size < 1 or page_size > 100:
            raise ServiceValidationError("Page size must be between 1 and 100")
        return self.repo.list_orders(page, page_size)

    def cleanup_expired_reservations(self) -> int:
        expired = self.repo.find_expired_reservations(datetime.utcnow())
        count = 0
        for reservation in expired:
            self._release_reservation(reservation)
            count += 1
        return count

    def _is_expired(self, reservation: Reservation) -> bool:
        return datetime.utcnow() > reservation.expires_at

    def _release_reservation(self, reservation: Reservation) -> None:
        if reservation.status == ReservationStatus.PENDING:
            self.repo.decrement_reserved_stock(reservation.sku_id, reservation.quantity)
        self.repo.update_reservation_status(reservation.id, ReservationStatus.EXPIRED)
