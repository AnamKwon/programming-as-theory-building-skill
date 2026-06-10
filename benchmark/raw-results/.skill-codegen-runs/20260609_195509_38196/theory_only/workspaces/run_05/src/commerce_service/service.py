from datetime import datetime

from .models import OrderState, ReservationState
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ReservationAlreadyConfirmedError(Exception):
    pass


class InvalidReservationStateError(Exception):
    pass


class OrderNotFoundError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class Service:
    def __init__(self, repository: Repository):
        self.repo = repository

    # SKU operations
    def create_sku(self, sku_id: str, name: str, initial_stock: int):
        sku = self.repo.create_sku(sku_id, name, initial_stock)
        return {
            "sku_id": sku.sku_id,
            "name": sku.name,
            "stock": sku.stock,
            "created_at": sku.created_at,
        }

    def adjust_stock(self, sku_id: str, delta: int):
        sku = self.repo.adjust_stock(sku_id, delta)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")
        return {
            "sku_id": sku.sku_id,
            "stock": sku.stock,
        }

    # Reservation operations
    def create_reservation(self, sku_id: str, quantity: int, idempotency_key: str):
        """Create a new reservation or return existing if idempotency key matches."""
        # Check for existing reservation with same idempotency key
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return {
                "reservation_id": existing.id,
                "sku_id": existing.sku_id,
                "quantity": existing.quantity,
                "state": existing.state,
                "expires_at": existing.expires_at,
                "created_at": existing.created_at,
            }

        # Check stock availability
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")
        if sku.stock < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku_id}: need {quantity}, have {sku.stock}"
            )

        # Create reservation
        reservation = self.repo.create_reservation(sku_id, quantity, idempotency_key)
        return {
            "reservation_id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "state": reservation.state,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

    def confirm_reservation(self, reservation_id: str, idempotency_key: str):
        """Confirm a pending reservation."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Check idempotency key matches
        if reservation.idempotency_key != idempotency_key:
            raise InvalidReservationStateError("Idempotency key mismatch")

        # Check reservation not expired
        if reservation.expires_at <= datetime.utcnow():
            self.repo.update_reservation_state(reservation_id, ReservationState.EXPIRED)
            raise ReservationExpiredError("Reservation has expired")

        # Check not already confirmed
        if reservation.state != ReservationState.PENDING:
            raise ReservationAlreadyConfirmedError(
                f"Reservation is {reservation.state}, cannot confirm"
            )

        # Deduct stock
        self.repo.adjust_stock(reservation.sku_id, -reservation.quantity)

        # Update reservation state
        updated = self.repo.update_reservation_state(
            reservation_id, ReservationState.CONFIRMED, confirmed_at=datetime.utcnow()
        )
        return {
            "reservation_id": updated.id,
            "sku_id": updated.sku_id,
            "quantity": updated.quantity,
            "state": updated.state,
            "expires_at": updated.expires_at,
            "created_at": updated.created_at,
        }

    def cancel_reservation(self, reservation_id: str, idempotency_key: str):
        """Cancel a reservation."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Check idempotency key matches
        if reservation.idempotency_key != idempotency_key:
            raise InvalidReservationStateError("Idempotency key mismatch")

        # Can only cancel pending or confirmed reservations
        if reservation.state not in [ReservationState.PENDING, ReservationState.CONFIRMED]:
            raise InvalidReservationStateError(
                f"Cannot cancel {reservation.state} reservation"
            )

        # Return stock if was confirmed
        if reservation.state == ReservationState.CONFIRMED:
            self.repo.adjust_stock(reservation.sku_id, reservation.quantity)

        # Update state
        updated = self.repo.update_reservation_state(
            reservation_id, ReservationState.CANCELLED
        )
        return {
            "reservation_id": updated.id,
            "sku_id": updated.sku_id,
            "quantity": updated.quantity,
            "state": updated.state,
            "expires_at": updated.expires_at,
            "created_at": updated.created_at,
        }

    # Order operations
    def create_order(self, reservation_id: str, idempotency_key: str):
        """Create an order from a confirmed reservation."""
        # Check for existing order with same idempotency key
        existing = self.repo.get_order_by_idempotency_key(idempotency_key)
        if existing:
            return {
                "order_id": existing.id,
                "reservation_id": existing.reservation_id,
                "sku_id": existing.sku_id,
                "quantity": existing.quantity,
                "state": existing.state,
                "created_at": existing.created_at,
                "updated_at": existing.updated_at,
            }

        # Get reservation
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Check reservation is confirmed
        if reservation.state != ReservationState.CONFIRMED:
            raise InvalidReservationStateError(
                f"Reservation must be confirmed, current state: {reservation.state}"
            )

        # Create order
        order = self.repo.create_order(
            reservation_id, reservation.sku_id, reservation.quantity, idempotency_key
        )
        return {
            "order_id": order.id,
            "reservation_id": order.reservation_id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "state": order.state,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }

    def get_order(self, order_id: str):
        """Get order details."""
        order = self.repo.get_order(order_id)
        if not order:
            raise OrderNotFoundError(f"Order {order_id} not found")
        return {
            "order_id": order.id,
            "reservation_id": order.reservation_id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "state": order.state,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }

    def list_orders(self, limit: int = 10, offset: int = 0):
        """List orders with pagination."""
        orders, total = self.repo.list_orders(limit=limit, offset=offset)
        return {
            "orders": [
                {
                    "order_id": o.id,
                    "reservation_id": o.reservation_id,
                    "sku_id": o.sku_id,
                    "quantity": o.quantity,
                    "state": o.state,
                    "created_at": o.created_at,
                    "updated_at": o.updated_at,
                }
                for o in orders
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
