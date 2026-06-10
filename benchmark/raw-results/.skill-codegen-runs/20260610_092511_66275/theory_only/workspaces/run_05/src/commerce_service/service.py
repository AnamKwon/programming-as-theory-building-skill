import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .models import ReservationStatus, OrderStatus
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ReservationAlreadyConfirmedError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class OrderNotFoundError(Exception):
    pass


class CommerceService:
    def __init__(self, session: Session):
        self.repo = Repository(session)
        self.session = session

    def create_sku(self, sku_id: str, name: str, description: str | None) -> dict:
        """Create a new SKU."""
        sku = self.repo.create_sku(sku_id, name, description)
        self.repo.get_or_create_stock(sku_id)
        self.repo.commit()
        return {
            "id": sku.id,
            "name": sku.name,
            "description": sku.description,
            "created_at": sku.created_at,
        }

    def adjust_stock(self, sku_id: str, quantity: int) -> dict:
        """Adjust stock level for a SKU (positive or negative)."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        stock = self.repo.update_stock(sku_id, available_delta=quantity)
        self.repo.commit()
        return {
            "sku_id": stock.sku_id,
            "available": stock.available,
            "reserved": stock.reserved,
        }

    def reserve_inventory(self, sku_id: str, quantity: int, idempotency_key: str) -> dict:
        """
        Create a reservation for inventory.
        Idempotency: retrying with same key returns same result.
        Expiration: 15 minutes.
        """
        # Check for existing reservation with this idempotency key
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == ReservationStatus.EXPIRED:
                raise ReservationExpiredError("Idempotent reservation has expired")
            return {
                "id": existing.id,
                "sku_id": existing.sku_id,
                "quantity": existing.quantity,
                "status": existing.status.value,
                "expires_at": existing.expires_at,
                "created_at": existing.created_at,
            }

        # Verify SKU exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        # Check stock availability
        stock = self.repo.get_stock(sku_id)
        if not stock or stock.available < quantity:
            raise InsufficientStockError(f"Insufficient stock for SKU {sku_id}")

        # Create reservation
        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        try:
            reservation = self.repo.create_reservation(
                reservation_id, sku_id, quantity, expires_at, idempotency_key
            )
            # Reserve stock
            self.repo.update_stock(sku_id, available_delta=-quantity, reserved_delta=quantity)
            self.repo.commit()
        except IntegrityError:
            self.repo.rollback()
            # Idempotency key collision; retry
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                return {
                    "id": existing.id,
                    "sku_id": existing.sku_id,
                    "quantity": existing.quantity,
                    "status": existing.status.value,
                    "expires_at": existing.expires_at,
                    "created_at": existing.created_at,
                }
            raise

        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status.value,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

    def confirm_reservation(self, reservation_id: str) -> dict:
        """Confirm a reservation and create an order."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Check if already confirmed
        if reservation.status != ReservationStatus.ACTIVE:
            raise ReservationAlreadyConfirmedError(
                f"Cannot confirm reservation in {reservation.status.value} status"
            )

        # Check expiration
        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            self.repo.commit()
            raise ReservationExpiredError("Reservation has expired")

        # Create order
        order_id = str(uuid.uuid4())
        order = self.repo.create_order(order_id, reservation_id, reservation.sku_id, reservation.quantity)

        # Update reservation status
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)
        self.repo.commit()

        return {
            "id": order.id,
            "reservation_id": order.reservation_id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "status": order.status.value,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }

    def cancel_reservation(self, reservation_id: str) -> dict:
        """Cancel a reservation and release reserved stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.ACTIVE:
            raise ReservationAlreadyConfirmedError(
                f"Cannot cancel reservation in {reservation.status.value} status"
            )

        # Release reserved stock
        self.repo.update_stock(
            reservation.sku_id, available_delta=reservation.quantity, reserved_delta=-reservation.quantity
        )
        # Update reservation status
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
        self.repo.commit()

        updated = self.repo.get_reservation(reservation_id)
        return {
            "id": updated.id,
            "sku_id": updated.sku_id,
            "quantity": updated.quantity,
            "status": updated.status.value,
            "expires_at": updated.expires_at,
            "created_at": updated.created_at,
        }

    def get_order(self, order_id: str) -> dict:
        """Retrieve an order."""
        order = self.repo.get_order(order_id)
        if not order:
            raise OrderNotFoundError(f"Order {order_id} not found")

        return {
            "id": order.id,
            "reservation_id": order.reservation_id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "status": order.status.value,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }

    def list_orders(self, cursor: str | None, limit: int) -> dict:
        """List orders with pagination."""
        orders, next_cursor = self.repo.get_orders_paginated(cursor, limit)
        return {
            "orders": [
                {
                    "id": order.id,
                    "reservation_id": order.reservation_id,
                    "sku_id": order.sku_id,
                    "quantity": order.quantity,
                    "status": order.status.value,
                    "created_at": order.created_at,
                    "updated_at": order.updated_at,
                }
                for order in orders
            ],
            "next_cursor": next_cursor,
        }

    def cleanup_expired_reservations(self):
        """Release stock from expired reservations."""
        expired = self.repo.get_expired_reservations(datetime.utcnow())
        for reservation in expired:
            if reservation.status == ReservationStatus.ACTIVE:
                self.repo.update_stock(
                    reservation.sku_id,
                    available_delta=reservation.quantity,
                    reserved_delta=-reservation.quantity,
                )
                self.repo.update_reservation_status(reservation.id, ReservationStatus.EXPIRED)
        if expired:
            self.repo.commit()
