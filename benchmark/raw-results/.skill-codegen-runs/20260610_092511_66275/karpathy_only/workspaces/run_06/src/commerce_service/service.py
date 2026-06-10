from datetime import datetime, timedelta

from .models import OrderStatus, Reservation, ReservationStatus
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class OrderNotFoundError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class CommerceService:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_code: str, name: str, description: str | None, stock_level: int):
        existing = self.repo.get_sku_by_code(sku_code)
        if existing:
            raise ValueError(f"SKU code {sku_code} already exists")
        return self.repo.create_sku(sku_code, name, description, stock_level)

    def adjust_stock(self, sku_id: int, quantity_change: int):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        if sku.stock_level + quantity_change < 0:
            raise ValueError(f"Cannot adjust stock below zero")
        return self.repo.adjust_stock(sku_id, quantity_change)

    def create_reservation(self, order_id: str, sku_id: int, quantity: int, idempotency_key: str):
        # Check idempotency: if this key was already processed, return existing reservation
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == ReservationStatus.CANCELLED or existing.status == ReservationStatus.EXPIRED:
                raise ValueError(f"Reservation for this request was previously cancelled or expired")
            return existing

        # Check SKU exists and has stock
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        if sku.stock_level < quantity:
            raise InsufficientStockError(f"Insufficient stock for SKU {sku_id}: need {quantity}, have {sku.stock_level}")

        # Reserve stock and create order/reservation
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        # Check if order already exists
        order = self.repo.get_order(order_id)
        if not order:
            order = self.repo.create_order(order_id, 0)

        # Create reservation and reduce stock
        reservation = self.repo.create_reservation(
            order_id=order_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

        self.repo.adjust_stock(sku_id, -quantity)
        order.total_items += quantity
        self.repo.session.commit()

        return reservation

    def confirm_reservation(self, reservation_id: int):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Check expiration
        if datetime.utcnow() > reservation.expires_at:
            self.repo.expire_reservation(reservation_id)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.status == ReservationStatus.CANCELLED:
            raise InvalidStateTransitionError(f"Cannot confirm cancelled reservation")

        if reservation.status == ReservationStatus.CONFIRMED:
            return reservation

        confirmed = self.repo.confirm_reservation(reservation_id)

        # If all reservations for order are confirmed, mark order as confirmed
        order = self.repo.get_order(reservation.order_id)
        if order:
            all_reservations = self.repo.get_reservations_by_order(reservation.order_id)
            if all(r.status == ReservationStatus.CONFIRMED for r in all_reservations):
                self.repo.confirm_order(reservation.order_id)

        return confirmed

    def cancel_reservation(self, reservation_id: int):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CANCELLED or reservation.status == ReservationStatus.EXPIRED:
            return reservation

        # Release reserved stock
        self.repo.adjust_stock(reservation.sku_id, reservation.quantity)
        order = self.repo.get_order(reservation.order_id)
        if order:
            order.total_items -= reservation.quantity
            self.repo.session.commit()

        return self.repo.cancel_reservation(reservation_id)

    def get_order(self, order_id: str):
        order = self.repo.get_order(order_id)
        if not order:
            raise OrderNotFoundError(f"Order {order_id} not found")
        return order

    def list_orders(self, limit: int = 20, offset: int = 0):
        return self.repo.list_orders(limit, offset)
