from datetime import datetime

from .models import OrderStatus, ReservationStatus
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidTransitionError(Exception):
    pass


class IdempotencyKeyAlreadyUsedError(Exception):
    pass


class CommerceService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku: str, description: str, quantity: int):
        return self.repo.create_sku(sku, description, quantity)

    def get_sku(self, sku: str):
        return self.repo.get_sku(sku)

    def adjust_stock(self, sku: str, adjustment: int):
        sku_model = self.repo.adjust_stock(sku, adjustment)
        if not sku_model:
            raise ValueError(f"SKU {sku} not found")
        return sku_model

    def create_reservation(
        self, order_id: str, sku: str, quantity: int, idempotency_key: str
    ):
        # Check idempotency: if this key was already used, return the existing reservation
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            # Idempotent: return the existing reservation
            return existing

        # Verify SKU exists and has sufficient stock
        sku_model = self.repo.get_sku(sku)
        if not sku_model:
            raise ValueError(f"SKU {sku} not found")
        if sku_model.quantity < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku}: need {quantity}, have {sku_model.quantity}"
            )

        # Create the reservation (does not deduct from stock yet)
        reservation = self.repo.create_reservation(order_id, sku, quantity, idempotency_key)

        # Ensure order exists
        order = self.repo.get_order(order_id)
        if not order:
            self.repo.create_order(order_id)

        return reservation

    def confirm_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Check expiration
        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED.value)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        # Only pending reservations can be confirmed
        if reservation.status != ReservationStatus.PENDING.value:
            raise InvalidTransitionError(
                f"Cannot confirm reservation in {reservation.status} state"
            )

        # Deduct from stock
        sku_model = self.repo.get_sku(reservation.sku)
        if not sku_model or sku_model.quantity < reservation.quantity:
            raise InsufficientStockError(
                f"Insufficient stock to confirm reservation for {reservation.sku}"
            )
        self.repo.adjust_stock(reservation.sku, -reservation.quantity)

        # Update reservation status
        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED.value
        )

        # Update order status if all reservations are confirmed
        order = self.repo.get_order(reservation.order_id)
        if order:
            reservations = self.repo.get_reservations_for_order(reservation.order_id)
            if all(r.status == ReservationStatus.CONFIRMED.value for r in reservations):
                self.repo.update_order_status(reservation.order_id, OrderStatus.CONFIRMED.value)

        return self.repo.get_reservation(reservation_id)

    def cancel_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Cannot cancel if already confirmed (stock already deducted)
        if reservation.status == ReservationStatus.CONFIRMED.value:
            raise InvalidTransitionError(
                f"Cannot cancel a confirmed reservation {reservation_id}"
            )

        # Mark as cancelled
        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED.value
        )

        return self.repo.get_reservation(reservation_id)

    def get_order(self, order_id: str):
        order = self.repo.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return order

    def list_orders(self, limit: int = 10, offset: int = 0):
        return self.repo.list_orders(limit, offset)

    def get_reservations_for_order(self, order_id: str):
        return self.repo.get_reservations_for_order(order_id)
