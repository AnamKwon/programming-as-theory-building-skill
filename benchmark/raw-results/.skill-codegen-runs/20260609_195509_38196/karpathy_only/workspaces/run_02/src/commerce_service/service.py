from datetime import datetime
from commerce_service.repository import Repository
from commerce_service.models import OrderStatus


class InsufficientStockError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class IdempotencyKeyConflictError(Exception):
    pass


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_code: str, name: str):
        return self.repo.create_sku(sku_code, name)

    def adjust_stock(self, sku_id: int, quantity_delta: int):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        if sku.available_quantity + quantity_delta < 0:
            raise ValueError("Cannot reduce available stock below 0")

        return self.repo.update_sku_stock(sku_id, available_delta=quantity_delta)

    def create_reservation(self, sku_id: int, quantity: int, idempotency_key: str):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        existing = self.repo.get_order_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == OrderStatus.CANCELLED:
                raise IdempotencyKeyConflictError("This idempotency key was already used for a cancelled reservation")
            return existing

        if sku.available_quantity < quantity:
            raise InsufficientStockError(f"Insufficient stock: need {quantity}, available {sku.available_quantity}")

        order = self.repo.create_order(sku_id, quantity, idempotency_key)
        self.repo.update_sku_stock(sku_id, available_delta=-quantity, reserved_delta=quantity)

        return order

    def confirm_reservation(self, order_id: int):
        order = self.repo.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        if order.status != OrderStatus.RESERVED:
            raise InvalidStateTransitionError(f"Can only confirm reserved orders; got {order.status}")

        if order.expires_at and datetime.utcnow() > order.expires_at:
            raise ReservationExpiredError(f"Reservation expired at {order.expires_at}")

        return self.repo.update_order_status(order_id, OrderStatus.CONFIRMED)

    def cancel_reservation(self, order_id: int):
        order = self.repo.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        if order.status == OrderStatus.CANCELLED:
            return order

        if order.status == OrderStatus.CONFIRMED:
            raise InvalidStateTransitionError("Cannot cancel confirmed reservations")

        if order.status == OrderStatus.RESERVED:
            self.repo.update_sku_stock(order.sku_id, available_delta=order.quantity, reserved_delta=-order.quantity)

        return self.repo.update_order_status(order_id, OrderStatus.CANCELLED)
