"""Business logic layer enforcing domain invariants."""
from datetime import datetime

from .repository import Repository
from .models import ReservationState, OrderState


class ServiceError(Exception):
    """Base exception for service errors."""
    pass


class InsufficientStockError(ServiceError):
    """Raised when stock is insufficient for a reservation."""
    pass


class ReservationNotFoundError(ServiceError):
    """Raised when reservation does not exist."""
    pass


class ReservationExpiredError(ServiceError):
    """Raised when attempting to confirm an expired reservation."""
    pass


class InvalidStateTransitionError(ServiceError):
    """Raised when state transition is invalid."""
    pass


class Service:
    """Application business logic layer."""

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku: str, name: str) -> dict:
        """Create a new SKU."""
        db_sku = self.repo.create_sku(sku, name)
        return {
            "id": db_sku.id,
            "sku": db_sku.sku,
            "name": db_sku.name,
            "created_at": db_sku.created_at,
        }

    def adjust_stock(self, sku_id: str, adjustment: int) -> dict:
        """Adjust inventory for a SKU."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ServiceError(f"SKU {sku_id} not found")

        available = self.repo.adjust_stock(sku_id, adjustment)
        available_qty, reserved_qty = self.repo.get_inventory(sku_id)
        return {
            "sku_id": sku_id,
            "available": available_qty,
            "reserved": reserved_qty,
        }

    def reserve(
        self,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
    ) -> dict:
        """
        Create a time-limited reservation for inventory.
        Idempotency key prevents duplicate reservations.
        """
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ServiceError(f"SKU {sku_id} not found")

        available, reserved = self.repo.get_inventory(sku_id)
        if available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku_id}: need {quantity}, available {available}"
            )

        reservation = self.repo.create_reservation(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
        )

        if not reservation:
            raise ServiceError(f"Idempotency key {idempotency_key} already used")

        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "state": reservation.state.value,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

    def confirm_reservation(self, reservation_id: int) -> dict:
        """
        Confirm a pending reservation, moving stock from available to reserved.
        Fails if reservation has expired or is not pending.
        """
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state != ReservationState.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in {reservation.state.value} state"
            )

        if datetime.utcnow() > reservation.expires_at:
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if not self.repo.reserve_stock(reservation.sku_id, reservation.quantity):
            raise InsufficientStockError(
                f"Cannot reserve {reservation.quantity} of {reservation.sku_id}"
            )

        self.repo.update_reservation_state(reservation_id, ReservationState.CONFIRMED)
        order = self.repo.create_order(reservation_id)

        return {
            "id": reservation_id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "state": ReservationState.CONFIRMED.value,
            "order_id": order.id,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        """Cancel a pending reservation, releasing its hold on inventory."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state != ReservationState.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot cancel reservation in {reservation.state.value} state"
            )

        self.repo.update_reservation_state(reservation_id, ReservationState.CANCELLED)

        return {
            "id": reservation_id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "state": ReservationState.CANCELLED.value,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

    def lookup_orders(self, page: int = 1, page_size: int = 10) -> dict:
        """List orders with pagination."""
        orders, total = self.repo.list_orders(page=page, page_size=page_size)
        return {
            "orders": [
                {
                    "id": order.id,
                    "reservation_id": order.reservation_id,
                    "state": order.state.value,
                    "created_at": order.created_at,
                }
                for order in orders
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": page * page_size < total,
        }
