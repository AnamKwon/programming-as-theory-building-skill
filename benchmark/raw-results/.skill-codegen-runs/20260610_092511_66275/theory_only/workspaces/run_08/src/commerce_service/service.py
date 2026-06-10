import uuid
from datetime import datetime

from .repository import Repository
from .models import ReservationModel, OrderModel


class ServiceError(Exception):
    pass


class ConflictError(ServiceError):
    pass


class NotFoundError(ServiceError):
    pass


class ValidationError(ServiceError):
    pass


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, name: str):
        existing = self.repo.get_sku(sku_id)
        if existing:
            raise ConflictError(f"SKU {sku_id} already exists")
        return self.repo.create_sku(sku_id, name)

    def adjust_stock(self, sku_id: str, delta: int):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise NotFoundError(f"SKU {sku_id} not found")
        inv = self.repo.adjust_stock(sku_id, delta)
        if inv.quantity < 0:
            raise ValidationError("Stock cannot be negative")
        return inv

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str
    ) -> tuple[str, OrderModel]:
        """Create a reservation and return (reservation_id, order)."""
        # Check for idempotency
        existing_res = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing_res:
            if existing_res.status == "cancelled":
                raise ValidationError("Idempotency key previously used and cancelled")
            order = self.repo.session.query(OrderModel).filter(
                OrderModel.reservation_id == existing_res.id
            ).first()
            if not order:
                raise ServiceError("Existing reservation has no order")
            return existing_res.id, order

        # Validate SKU exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise NotFoundError(f"SKU {sku_id} not found")

        # Check stock availability
        inv = self.repo.get_inventory(sku_id)
        if not inv or (inv.quantity - inv.reserved) < quantity:
            raise ValidationError(f"Insufficient stock for SKU {sku_id}")

        # Create reservation
        reservation_id = str(uuid.uuid4())
        reservation = self.repo.create_reservation(reservation_id, sku_id, quantity, idempotency_key)

        # Reserve stock
        self.repo.reserve_stock(sku_id, quantity)

        # Create pending order
        order_id = str(uuid.uuid4())
        order = self.repo.create_order(order_id, reservation_id, sku_id, quantity, "pending")

        return reservation_id, order

    def confirm_reservation(self, reservation_id: str) -> OrderModel:
        """Confirm a reservation and update order status."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise NotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == "cancelled":
            raise ValidationError("Cannot confirm a cancelled reservation")

        if reservation.is_expired():
            raise ValidationError("Reservation has expired")

        # Update reservation status
        self.repo.update_reservation_status(reservation_id, "confirmed")

        # Update order status
        order = self.repo.session.query(OrderModel).filter(
            OrderModel.reservation_id == reservation_id
        ).first()
        if not order:
            raise ServiceError(f"Order for reservation {reservation_id} not found")

        order = self.repo.update_order_status(order.id, "confirmed")
        return order

    def cancel_reservation(self, reservation_id: str) -> OrderModel:
        """Cancel a reservation and release stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise NotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == "cancelled":
            raise ValidationError("Reservation is already cancelled")

        if reservation.status == "confirmed":
            raise ValidationError("Cannot cancel a confirmed reservation")

        # Release reserved stock
        self.repo.release_reserved_stock(reservation.sku_id, reservation.quantity)

        # Update reservation status
        self.repo.update_reservation_status(reservation_id, "cancelled")

        # Update order status
        order = self.repo.session.query(OrderModel).filter(
            OrderModel.reservation_id == reservation_id
        ).first()
        if not order:
            raise ServiceError(f"Order for reservation {reservation_id} not found")

        order = self.repo.update_order_status(order.id, "cancelled")
        return order

    def get_order(self, order_id: str) -> OrderModel:
        order = self.repo.get_order(order_id)
        if not order:
            raise NotFoundError(f"Order {order_id} not found")
        return order

    def list_orders(self, page: int = 1, size: int = 10) -> tuple[list[OrderModel], int]:
        if page < 1 or size < 1:
            raise ValidationError("page and size must be >= 1")
        if size > 100:
            raise ValidationError("size must be <= 100")
        return self.repo.get_orders_paginated(page, size)
