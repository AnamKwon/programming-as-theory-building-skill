import uuid
from datetime import datetime, timedelta

from .repository import (
    Repository,
    RepositoryError,
    SKUNotFoundError,
    DuplicateIdempotencyKeyError,
)
from .models import ReservationStatus, SKUModel, ReservationModel, OrderModel


class ServiceError(Exception):
    pass


class InsufficientStockError(ServiceError):
    pass


class ReservationNotFoundError(ServiceError):
    pass


class ReservationAlreadyConfirmedError(ServiceError):
    pass


class ReservationExpiredError(ServiceError):
    pass


class Service:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, name: str) -> SKUModel:
        return self.repo.create_sku(sku_id, name)

    def adjust_stock(self, sku_id: str, quantity: int) -> SKUModel:
        try:
            return self.repo.adjust_stock(sku_id, quantity)
        except SKUNotFoundError:
            raise ServiceError(f"SKU {sku_id} not found")

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str
    ) -> ReservationModel:
        existing = self.repo.get_reservation_by_key(idempotency_key)
        if existing:
            return existing

        try:
            sku = self.repo.get_sku(sku_id)
        except SKUNotFoundError:
            raise ServiceError(f"SKU {sku_id} not found")

        if sku.available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku_id}: have {sku.available}, need {quantity}"
            )

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        try:
            reservation = self.repo.create_reservation(
                reservation_id=reservation_id,
                sku_id=sku_id,
                quantity=quantity,
                idempotency_key=idempotency_key,
                expires_at=expires_at,
            )
        except DuplicateIdempotencyKeyError:
            return self.repo.get_reservation_by_key(idempotency_key)

        sku.available -= quantity
        sku.reserved += quantity
        self.repo.session.commit()

        return reservation

    def confirm_reservation(self, reservation_id: str) -> OrderModel:
        try:
            reservation = self.repo.get_reservation(reservation_id)
        except RepositoryError:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CONFIRMED:
            raise ReservationAlreadyConfirmedError(
                f"Reservation {reservation_id} already confirmed"
            )

        if reservation.status == ReservationStatus.CANCELLED:
            raise ServiceError(f"Reservation {reservation_id} is cancelled")

        if reservation.status == ReservationStatus.EXPIRED:
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(
                reservation_id, ReservationStatus.EXPIRED
            )
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED
        )

        order_id = str(uuid.uuid4())
        order = self.repo.create_order(
            order_id=order_id,
            reservation_id=reservation_id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
        )

        sku = self.repo.get_sku(reservation.sku_id)
        sku.reserved -= reservation.quantity
        self.repo.session.commit()

        return order

    def cancel_reservation(self, reservation_id: str) -> ReservationModel:
        try:
            reservation = self.repo.get_reservation(reservation_id)
        except RepositoryError:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.PENDING:
            raise ServiceError(f"Cannot cancel reservation with status {reservation.status}")

        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED
        )

        sku = self.repo.get_sku(reservation.sku_id)
        sku.available += reservation.quantity
        sku.reserved -= reservation.quantity
        self.repo.session.commit()

        return self.repo.get_reservation(reservation_id)

    def get_orders(self, offset: int = 0, limit: int = 10) -> tuple[list[OrderModel], int]:
        return self.repo.get_orders(offset, limit)

    def expire_reservations(self) -> int:
        return self.repo.mark_expired_reservations(datetime.utcnow())
