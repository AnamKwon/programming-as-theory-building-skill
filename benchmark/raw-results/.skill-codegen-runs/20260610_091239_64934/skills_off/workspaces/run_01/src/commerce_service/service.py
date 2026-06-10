import uuid
from datetime import datetime, timedelta
from typing import Optional

from .models import OrderState, ReservationRequest, ReservationState
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class CommerceService:
    RESERVATION_TTL_MINUTES = 30

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, name: str, quantity: int):
        """Create a new SKU with initial stock."""
        return self.repo.create_sku(sku_id, name, quantity)

    def adjust_stock(self, sku_id: str, quantity: int):
        """Adjust stock for a SKU."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")
        return self.repo.adjust_stock(sku_id, quantity)

    def reserve(self, request: ReservationRequest):
        """
        Create a reservation for a SKU.

        Returns existing reservation if idempotency key matches.
        Raises InsufficientStockError if stock unavailable.
        """
        # Check for idempotent retry
        existing = self.repo.get_reservation_by_idempotency_key(request.idempotency_key)
        if existing:
            return existing

        # Verify SKU exists
        sku = self.repo.get_sku(request.sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {request.sku_id} not found")

        # Check stock availability
        total_available = sku.available_stock - sku.reserved_stock
        if total_available < request.quantity:
            raise InsufficientStockError(
                f"Insufficient stock: requested {request.quantity}, available {total_available}"
            )

        # Create reservation
        res_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        reservation = self.repo.create_reservation(
            res_id, request.sku_id, request.quantity, expires_at, request.idempotency_key
        )

        # Reserve stock
        sku.reserved_stock += request.quantity
        self.repo.session.commit()

        return reservation

    def confirm_reservation(self, res_id: str):
        """
        Confirm a pending reservation.

        Moves reservation to confirmed and locks the stock.
        Raises ReservationExpiredError if reservation has expired.
        Raises ReservationNotFoundError if reservation doesn't exist.
        """
        reservation = self.repo.get_reservation(res_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {res_id} not found")

        if reservation.expires_at <= datetime.utcnow():
            self.repo.update_reservation_state(res_id, ReservationState.EXPIRED)
            raise ReservationExpiredError(f"Reservation {res_id} has expired")

        if reservation.state != ReservationState.PENDING:
            return reservation

        # Confirm reservation and lock stock
        sku = self.repo.get_sku(reservation.sku_id)
        if sku:
            sku.available_stock -= reservation.quantity
            sku.reserved_stock -= reservation.quantity
            self.repo.session.commit()

        return self.repo.update_reservation_state(res_id, ReservationState.CONFIRMED)

    def cancel_reservation(self, res_id: str):
        """
        Cancel a reservation and return reserved stock.

        Raises ReservationNotFoundError if reservation doesn't exist.
        """
        reservation = self.repo.get_reservation(res_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {res_id} not found")

        if reservation.state == ReservationState.CANCELLED:
            return reservation

        # Return reserved stock
        sku = self.repo.get_sku(reservation.sku_id)
        if sku and reservation.state == ReservationState.PENDING:
            sku.reserved_stock -= reservation.quantity
            self.repo.session.commit()

        return self.repo.update_reservation_state(res_id, ReservationState.CANCELLED)

    def get_order(self, order_id: str):
        """Get order by ID."""
        order = self.repo.get_order(order_id)
        if not order:
            raise ReservationNotFoundError(f"Order {order_id} not found")
        return order

    def list_orders(self, page: int = 1, size: int = 20):
        """List orders with pagination."""
        return self.repo.list_orders(page, size)

    def create_order(self, reservation_ids: list[str]):
        """Create an order from reservations."""
        order_id = str(uuid.uuid4())
        order = self.repo.create_order(order_id)

        for res_id in reservation_ids:
            reservation = self.repo.get_reservation(res_id)
            if not reservation:
                raise ReservationNotFoundError(f"Reservation {res_id} not found")
            self.repo.add_item_to_order(order_id, res_id)

        return order

    def cleanup_expired_reservations(self):
        """Mark expired reservations and return reserved stock."""
        now = datetime.utcnow()
        expired = self.repo.list_expired_reservations(now)

        for reservation in expired:
            sku = self.repo.get_sku(reservation.sku_id)
            if sku:
                sku.reserved_stock -= reservation.quantity
                self.repo.session.commit()
            self.repo.update_reservation_state(reservation.id, ReservationState.EXPIRED)

        return expired
