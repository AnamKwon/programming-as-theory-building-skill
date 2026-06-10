"""Business logic layer for commerce service."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .models import (
    OrderModel,
    ReservationModel,
    ReservationStatus,
    SKUModel,
)
from .repository import Repository


class ConflictError(Exception):
    """Raised when business logic constraint is violated."""

    pass


class NotFoundError(Exception):
    """Raised when resource is not found."""

    pass


class Service:
    """Business logic layer."""

    RESERVATION_TTL_MINUTES = 10

    def __init__(self, session: Session):
        self.session = session
        self.repo = Repository(session)

    def create_sku(self, sku_id: str, name: str, stock: int) -> SKUModel:
        existing = self.repo.get_sku(sku_id)
        if existing:
            raise ConflictError(f"SKU {sku_id} already exists")
        return self.repo.create_sku(sku_id, name, stock)

    def adjust_stock(self, sku_id: str, delta: int) -> SKUModel:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise NotFoundError(f"SKU {sku_id} not found")
        if sku.stock + delta < 0:
            raise ConflictError(f"Stock cannot be negative")
        return self.repo.update_sku_stock(sku_id, delta)

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str
    ) -> ReservationModel:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == ReservationStatus.PENDING:
                self._check_reservation_expired(existing)
            return existing

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise NotFoundError(f"SKU {sku_id} not found")

        available_stock = self._calculate_available_stock(sku_id)
        if available_stock < quantity:
            raise ConflictError(
                f"Insufficient stock. Available: {available_stock}, Requested: {quantity}"
            )

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)
        reservation = self.repo.create_reservation(
            reservation_id, sku_id, quantity, expires_at, idempotency_key
        )
        return reservation

    def confirm_reservation(self, reservation_id: str) -> OrderModel:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise NotFoundError(f"Reservation {reservation_id} not found")

        self._check_reservation_expired(reservation)

        if reservation.status != ReservationStatus.PENDING:
            raise ConflictError(
                f"Reservation {reservation_id} status is {reservation.status}, cannot confirm"
            )

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

        sku = self.repo.get_sku(reservation.sku_id)
        if not sku:
            raise NotFoundError(f"SKU {reservation.sku_id} not found")
        self.repo.update_sku_stock(reservation.sku_id, -reservation.quantity)

        order_id = str(uuid.uuid4())
        order = self.repo.create_order(order_id, reservation_id, reservation.sku_id, reservation.quantity)
        return order

    def cancel_reservation(self, reservation_id: str) -> ReservationModel:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise NotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.PENDING:
            raise ConflictError(
                f"Reservation {reservation_id} status is {reservation.status}, cannot cancel"
            )

        return self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

    def get_orders(self, page: int = 1, page_size: int = 20) -> tuple[list[OrderModel], int]:
        if page < 1:
            raise ValueError("Page must be >= 1")
        if page_size < 1 or page_size > 100:
            raise ValueError("Page size must be between 1 and 100")
        return self.repo.list_orders(page, page_size)

    def _calculate_available_stock(self, sku_id: str) -> int:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            return 0

        reserved_quantity = sum(
            r.quantity
            for r in self.repo.get_pending_reservations_for_sku(sku_id)
            if not self._is_reservation_expired(r)
        )
        return sku.stock - reserved_quantity

    def _is_reservation_expired(self, reservation: ReservationModel) -> bool:
        return datetime.utcnow() > reservation.expires_at

    def _check_reservation_expired(self, reservation: ReservationModel) -> None:
        if self._is_reservation_expired(reservation):
            self.repo.update_reservation_status(reservation.id, ReservationStatus.EXPIRED)
            raise ConflictError(f"Reservation {reservation.id} has expired")
