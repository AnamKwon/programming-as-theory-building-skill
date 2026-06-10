from datetime import datetime

from .models import ReservationResponse, ReservationState, SKUResponse
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ReservationAlreadyConfirmedError(Exception):
    pass


class ReservationAlreadyCancelledError(Exception):
    pass


class SkuNotFoundError(Exception):
    pass


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, name: str, initial_stock: int) -> SKUResponse:
        return self.repo.create_sku(sku_id, name, initial_stock)

    def adjust_stock(self, sku_id: str, quantity_delta: int) -> SKUResponse:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SkuNotFoundError(f"SKU {sku_id} not found")
        return self.repo.adjust_stock(sku_id, quantity_delta)

    def create_reservation(
        self, customer_id: str, sku_id: str, quantity: int, idempotency_key: str
    ) -> ReservationResponse:
        # Idempotency: check if this exact request was already processed
        existing = self.repo.find_reservation_by_idempotency_key(customer_id, idempotency_key)
        if existing and existing.state == ReservationState.PENDING:
            return existing

        # Availability: ensure stock exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SkuNotFoundError(f"SKU {sku_id} not found")

        if sku.available_stock < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku_id}. Available: {sku.available_stock}, Requested: {quantity}"
            )

        return self.repo.create_reservation(customer_id, sku_id, quantity, idempotency_key)

    def confirm_reservation(self, reservation_id: str) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if self._is_expired(reservation):
            self.repo.update_reservation_state(reservation_id, ReservationState.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.state == ReservationState.CONFIRMED:
            raise ReservationAlreadyConfirmedError(f"Reservation {reservation_id} is already confirmed")

        if reservation.state == ReservationState.CANCELLED:
            raise ReservationAlreadyCancelledError(f"Reservation {reservation_id} has been cancelled")

        return self.repo.update_reservation_state(reservation_id, ReservationState.CONFIRMED)

    def cancel_reservation(self, reservation_id: str) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state == ReservationState.CANCELLED:
            raise ReservationAlreadyCancelledError(f"Reservation {reservation_id} is already cancelled")

        if reservation.state == ReservationState.CONFIRMED:
            raise ReservationAlreadyConfirmedError(f"Cannot cancel a confirmed reservation")

        return self.repo.update_reservation_state(reservation_id, ReservationState.CANCELLED)

    def create_order_from_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state != ReservationState.CONFIRMED:
            raise ValueError(f"Only confirmed reservations can become orders")

        return self.repo.create_order(reservation)

    def list_orders(self, limit: int = 10, offset: int = 0):
        return self.repo.list_orders(limit, offset)

    @staticmethod
    def _is_expired(reservation: ReservationResponse) -> bool:
        return datetime.utcnow() > reservation.expires_at
