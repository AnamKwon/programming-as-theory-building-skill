import uuid
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.exc import IntegrityError

from .models import ReservationStatus, OrderStatus
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class InvalidReservationStatusError(Exception):
    pass


class IdempotencyConflictError(Exception):
    pass


class CommerceService:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku_id: str, name: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock."""
        sku = self.repo.create_sku(sku_id, name, initial_stock)
        return {
            "sku_id": sku.sku_id,
            "name": sku.name,
            "available_stock": sku.available_stock,
            "reserved_stock": sku.reserved_stock,
            "created_at": sku.created_at,
        }

    def adjust_stock(self, sku_id: str, adjustment: int) -> dict:
        """Adjust available stock (positive or negative)."""
        try:
            sku = self.repo.adjust_stock(sku_id, adjustment)
        except ValueError:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        return {
            "sku_id": sku.sku_id,
            "name": sku.name,
            "available_stock": sku.available_stock,
            "reserved_stock": sku.reserved_stock,
        }

    def create_reservation(
        self,
        sku_id: str,
        customer_id: str,
        quantity: int,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """Create a reservation for a customer. Idempotent if key provided."""
        # Check for idempotency
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                if existing.status == ReservationStatus.CANCELLED:
                    raise IdempotencyConflictError("Idempotency key was already used (cancelled)")
                # Return existing reservation if not cancelled
                return self._reservation_to_dict(existing)

        # Verify SKU exists and has stock
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")
        if sku.available_stock < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku_id}. Available: {sku.available_stock}, Requested: {quantity}"
            )

        # Create reservation
        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        try:
            reservation = self.repo.create_reservation(
                reservation_id=reservation_id,
                sku_id=sku_id,
                customer_id=customer_id,
                quantity=quantity,
                expires_at=expires_at,
                idempotency_key=idempotency_key,
            )
            # Reserve stock
            self.repo.update_sku_reserved_stock(sku_id, quantity)
            # Decrement available stock
            self.repo.adjust_stock(sku_id, -quantity)
        except IntegrityError:
            raise IdempotencyConflictError("Idempotency key already exists")

        return self._reservation_to_dict(reservation)

    def confirm_reservation(self, reservation_id: str) -> dict:
        """Confirm a reservation and create an order."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Check if expired
        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        # Check if already confirmed or cancelled
        if reservation.status == ReservationStatus.CONFIRMED:
            raise InvalidReservationStatusError(
                f"Reservation already confirmed"
            )
        if reservation.status == ReservationStatus.CANCELLED:
            raise InvalidReservationStatusError(
                f"Reservation has been cancelled"
            )

        # Create order
        order_id = str(uuid.uuid4())
        order = self.repo.create_order(
            order_id=order_id,
            reservation_id=reservation_id,
            sku_id=reservation.sku_id,
            customer_id=reservation.customer_id,
            quantity=reservation.quantity,
        )

        # Update reservation status
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

        # Decrement reserved stock
        self.repo.update_sku_reserved_stock(reservation.sku_id, -reservation.quantity)

        return self._order_to_dict(order)

    def cancel_reservation(self, reservation_id: str) -> dict:
        """Cancel a reservation and release reserved stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CANCELLED:
            raise InvalidReservationStatusError("Reservation already cancelled")
        if reservation.status == ReservationStatus.CONFIRMED:
            raise InvalidReservationStatusError(
                "Cannot cancel a confirmed reservation (order already exists)"
            )

        # Update status
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

        # Release reserved stock back to available
        self.repo.update_sku_reserved_stock(reservation.sku_id, -reservation.quantity)
        self.repo.adjust_stock(reservation.sku_id, reservation.quantity)

        return self._reservation_to_dict(reservation)

    def get_order(self, order_id: str) -> dict:
        """Retrieve an order by ID."""
        order = self.repo.get_order(order_id)
        if not order:
            raise Exception(f"Order {order_id} not found")
        return self._order_to_dict(order)

    def list_orders(self, customer_id: str, skip: int = 0, limit: int = 10) -> dict:
        """List orders for a customer with pagination."""
        orders = self.repo.list_orders(customer_id, skip, limit)
        total = self.repo.count_orders(customer_id)
        return {
            "items": [self._order_to_dict(order) for order in orders],
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    def _reservation_to_dict(self, reservation) -> dict:
        return {
            "reservation_id": reservation.reservation_id,
            "sku_id": reservation.sku_id,
            "customer_id": reservation.customer_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

    def _order_to_dict(self, order) -> dict:
        return {
            "order_id": order.order_id,
            "reservation_id": order.reservation_id,
            "sku_id": order.sku_id,
            "customer_id": order.customer_id,
            "quantity": order.quantity,
            "status": order.status,
            "created_at": order.created_at,
        }
