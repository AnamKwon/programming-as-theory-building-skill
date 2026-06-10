import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from commerce_service.models import Order, OrderState, Reservation, ReservationState, SKU
from commerce_service.repository import Repository


class ServiceError(Exception):
    pass


class InsufficientStockError(ServiceError):
    pass


class ReservationNotFoundError(ServiceError):
    pass


class ReservationExpiredError(ServiceError):
    pass


class ReservationStateError(ServiceError):
    pass


class OrderNotFoundError(ServiceError):
    pass


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, initial_stock: int) -> SKU:
        return self.repo.create_sku(sku_id, initial_stock)

    def get_sku(self, sku_id: str) -> SKU:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ServiceError(f"SKU {sku_id} not found")
        return sku

    def adjust_stock(self, sku_id: str, adjustment: int) -> SKU:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ServiceError(f"SKU {sku_id} not found")

        new_available = sku.available_stock + adjustment
        if new_available < 0:
            raise ServiceError(f"Cannot adjust stock below 0")

        sku.available_stock = new_available
        self.repo.update_sku(sku)
        return sku

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str, ttl_seconds: int
    ) -> Reservation:
        cached = self.repo.check_idempotency(idempotency_key)
        if cached:
            reservation_id = json.loads(cached)["reservation_id"]
            return self.repo.get_reservation(reservation_id)

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ServiceError(f"SKU {sku_id} not found")

        if not sku.can_reserve(quantity):
            raise InsufficientStockError(
                f"Insufficient stock: {sku.available_stock} available, {quantity} requested"
            )

        sku.reserve(quantity)
        self.repo.update_sku(sku)

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        reservation = Reservation(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            state=ReservationState.PENDING,
            expires_at=expires_at,
        )
        self.repo.create_reservation(reservation)

        result = json.dumps({"reservation_id": reservation_id})
        self.repo.record_idempotency(idempotency_key, "create_reservation", result)

        return reservation

    def confirm_reservation(
        self, reservation_id: str, idempotency_key: str
    ) -> Reservation:
        cached = self.repo.check_idempotency(idempotency_key)
        if cached:
            return self.repo.get_reservation(reservation_id)

        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.is_expired():
            reservation.cancel()
            self.repo.update_reservation(reservation)
            sku = self.repo.get_sku(reservation.sku_id)
            sku.release(reservation.quantity)
            self.repo.update_sku(sku)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.state != ReservationState.PENDING:
            raise ReservationStateError(
                f"Reservation must be pending, is {reservation.state}"
            )

        reservation.confirm()
        self.repo.update_reservation(reservation)

        self.repo.record_idempotency(idempotency_key, "confirm_reservation", "{}")

        return reservation

    def cancel_reservation(self, reservation_id: str) -> Reservation:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state == ReservationState.CANCELLED:
            return reservation

        sku = self.repo.get_sku(reservation.sku_id)
        sku.release(reservation.quantity)
        self.repo.update_sku(sku)

        reservation.cancel()
        self.repo.update_reservation(reservation)

        return reservation

    def create_order(
        self, reservation_ids: list[str], idempotency_key: str
    ) -> Order:
        cached = self.repo.check_idempotency(idempotency_key)
        if cached:
            order_id = json.loads(cached)["order_id"]
            return self.repo.get_order(order_id)

        for res_id in reservation_ids:
            res = self.repo.get_reservation(res_id)
            if not res:
                raise ReservationNotFoundError(f"Reservation {res_id} not found")
            if res.state != ReservationState.CONFIRMED:
                raise ReservationStateError(
                    f"Reservation {res_id} must be confirmed, is {res.state}"
                )

        order_id = str(uuid.uuid4())
        order = Order(order_id, reservation_ids, OrderState.PENDING)
        self.repo.create_order(order)

        result = json.dumps({"order_id": order_id})
        self.repo.record_idempotency(idempotency_key, "create_order", result)

        return order

    def get_order(self, order_id: str) -> Order:
        order = self.repo.get_order(order_id)
        if not order:
            raise OrderNotFoundError(f"Order {order_id} not found")
        return order

    def list_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[Order], int]:
        return self.repo.list_orders(page, page_size)

    def cleanup_expired_reservations(self) -> int:
        expired = self.repo.get_expired_reservations()
        count = 0
        for reservation in expired:
            sku = self.repo.get_sku(reservation.sku_id)
            sku.release(reservation.quantity)
            self.repo.update_sku(sku)
            reservation.cancel()
            self.repo.update_reservation(reservation)
            count += 1
        return count
