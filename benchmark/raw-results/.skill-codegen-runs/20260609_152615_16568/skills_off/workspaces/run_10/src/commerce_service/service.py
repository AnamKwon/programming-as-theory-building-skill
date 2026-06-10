from datetime import datetime
from typing import Optional

from commerce_service.models import ReservationStatus, OrderStatus, OrderModel, ReservationModel, SKUModel
from commerce_service.repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_code: str) -> SKUModel:
        return self.repo.create_sku(sku_code)

    def adjust_stock(self, sku_id: int, delta: int) -> SKUModel:
        sku = self.repo.update_stock(sku_id, delta)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return sku

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: Optional[str] = None,
    ) -> ReservationModel:
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        if sku.stock_available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock: available={sku.stock_available}, requested={quantity}"
            )

        reservation = self.repo.create_reservation(sku_id, quantity, idempotency_key)
        return reservation

    def confirm_reservation(self, reservation_id: int) -> tuple[ReservationModel, OrderModel]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.EXPIRED:
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.expires_at < datetime.utcnow():
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.status != ReservationStatus.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation with status {reservation.status}"
            )

        sku = self.repo.get_sku(reservation.sku_id)
        if not sku:
            raise ValueError(f"SKU {reservation.sku_id} not found")

        if sku.stock_available < reservation.quantity:
            raise InsufficientStockError(
                f"Insufficient stock for confirmation: available={sku.stock_available}, reserved={reservation.quantity}"
            )

        order = self.repo.create_order()
        self.repo.update_reservation_order(reservation_id, order.id)
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)
        self.repo.update_stock(reservation.sku_id, -reservation.quantity)

        return reservation, order

    def cancel_reservation(self, reservation_id: int) -> ReservationModel:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status not in (ReservationStatus.PENDING, ReservationStatus.EXPIRED):
            raise InvalidStateTransitionError(
                f"Cannot cancel reservation with status {reservation.status}"
            )

        return self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

    def get_order(self, order_id: int) -> Optional[OrderModel]:
        return self.repo.get_order(order_id)

    def list_orders(self, offset: int = 0, limit: int = 20) -> tuple[list[OrderModel], int]:
        return self.repo.list_orders(offset, limit)
