import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from .models import OrderStatus, ReservationStatus
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidReservationStateError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class OrderNotFoundError(Exception):
    pass


class CommerceService:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, product_id: str, name: str, initial_stock: int) -> dict:
        sku = self.repo.create_sku(product_id, name, initial_stock)
        return {
            "product_id": sku.product_id,
            "name": sku.name,
            "current_stock": sku.current_stock,
            "created_at": sku.created_at,
        }

    def adjust_stock(self, product_id: str, delta: int) -> dict:
        sku = self.repo.adjust_stock(product_id, delta)
        if not sku:
            raise SKUNotFoundError(f"SKU {product_id} not found")
        return {
            "product_id": sku.product_id,
            "name": sku.name,
            "current_stock": sku.current_stock,
            "created_at": sku.created_at,
        }

    def create_reservation(self, product_id: str, quantity: int, idempotency_key: str) -> dict:
        # Check for duplicate reservation with idempotency key
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            # Return existing reservation if not expired
            if existing.expires_at > datetime.now(timezone.utc):
                return self._reservation_to_dict(existing)
            else:
                # Expired, treat as new request
                pass

        # Check SKU exists and has stock
        sku = self.repo.get_sku(product_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {product_id} not found")

        if sku.current_stock < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {product_id}: requested {quantity}, available {sku.current_stock}"
            )

        # Create reservation
        reservation_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        reservation = self.repo.create_reservation(
            reservation_id=reservation_id,
            product_id=product_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )

        # Create associated order in RESERVED state
        order_id = str(uuid.uuid4())
        self.repo.create_order(order_id=order_id, reservation_id=reservation_id, product_id=product_id, quantity=quantity)

        return self._reservation_to_dict(reservation)

    def confirm_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.expires_at <= datetime.now(timezone.utc):
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.status != ReservationStatus.PENDING:
            raise InvalidReservationStateError(
                f"Cannot confirm reservation in {reservation.status} state"
            )

        # Reduce stock
        sku = self.repo.get_sku(reservation.product_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {reservation.product_id} not found")

        sku.current_stock -= reservation.quantity

        # Update reservation and order status
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)
        # Find associated order and update it
        order = None
        for ord in self.repo.session.query(self.repo.session.query(type(None)).from_statement(
            f"SELECT * FROM orders WHERE reservation_id = '{reservation_id}' LIMIT 1"
        )):
            pass

        # Simpler approach: query the order directly
        from sqlalchemy import select
        from .models import Order
        stmt = select(Order).where(Order.reservation_id == reservation_id).limit(1)
        order = self.repo.session.scalars(stmt).first()

        if order:
            self.repo.update_order_status(order.id, OrderStatus.CONFIRMED)

        return self._reservation_to_dict(self.repo.get_reservation(reservation_id))

    def cancel_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CANCELLED:
            raise InvalidReservationStateError("Reservation is already cancelled")

        if reservation.status == ReservationStatus.CONFIRMED:
            raise InvalidReservationStateError("Cannot cancel a confirmed reservation")

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

        # Update associated order
        from sqlalchemy import select
        from .models import Order
        stmt = select(Order).where(Order.reservation_id == reservation_id).limit(1)
        order = self.repo.session.scalars(stmt).first()

        if order:
            self.repo.update_order_status(order.id, OrderStatus.CANCELLED)

        return self._reservation_to_dict(self.repo.get_reservation(reservation_id))

    def get_order(self, order_id: str) -> dict:
        order = self.repo.get_order(order_id)
        if not order:
            raise OrderNotFoundError(f"Order {order_id} not found")
        return {
            "id": order.id,
            "reservation_id": order.reservation_id,
            "product_id": order.product_id,
            "quantity": order.quantity,
            "status": order.status,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }

    def list_orders(self, limit: int = 10, offset: int = 0) -> dict:
        orders, total = self.repo.list_orders(limit=limit, offset=offset)
        return {
            "orders": [
                {
                    "id": order.id,
                    "reservation_id": order.reservation_id,
                    "product_id": order.product_id,
                    "quantity": order.quantity,
                    "status": order.status,
                    "created_at": order.created_at,
                    "updated_at": order.updated_at,
                }
                for order in orders
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def _reservation_to_dict(self, reservation) -> dict:
        return {
            "id": reservation.id,
            "product_id": reservation.product_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
        }
