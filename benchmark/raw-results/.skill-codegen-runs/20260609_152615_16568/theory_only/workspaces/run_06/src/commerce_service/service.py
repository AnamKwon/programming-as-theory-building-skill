from datetime import datetime
from .repository import Repository
from .models import (
    ReservationModel,
    OrderModel,
    ReservationStatus,
)


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class InvalidReservationStateError(Exception):
    pass


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, available_stock: int):
        """Create a new SKU with initial stock."""
        return self.repo.create_sku(sku_id, available_stock)

    def adjust_stock(self, sku_id: str, delta: int):
        """Adjust stock level for a SKU."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return self.repo.adjust_stock(sku_id, delta)

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str
    ) -> tuple[ReservationModel, bool]:
        """
        Create a reservation for a SKU.
        Returns (reservation, is_new).
        If idempotency_key already exists, returns existing reservation with is_new=False.
        Raises InsufficientStockError if not enough stock available.
        """
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        reserved = self.repo.get_reserved_stock(sku_id)
        available = sku.available_stock - reserved

        if quantity > available:
            raise InsufficientStockError(
                f"Insufficient stock. Requested: {quantity}, Available: {available}"
            )

        return self.repo.create_reservation(sku_id, quantity, idempotency_key)

    def confirm_reservation(self, reservation_id: str) -> OrderModel:
        """
        Confirm a reservation and convert it to an order.
        Raises ReservationNotFoundError if reservation does not exist.
        Raises InvalidReservationStateError if reservation cannot be confirmed.
        """
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        try:
            return self.repo.confirm_reservation(reservation_id)
        except ValueError as e:
            if "expired" in str(e).lower():
                raise InvalidReservationStateError(str(e))
            raise InvalidReservationStateError(str(e))

    def cancel_reservation(self, reservation_id: str) -> ReservationModel:
        """
        Cancel a reservation.
        Raises ReservationNotFoundError if reservation does not exist.
        """
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        try:
            return self.repo.cancel_reservation(reservation_id)
        except ValueError as e:
            raise InvalidReservationStateError(str(e))

    def list_orders(self, page: int = 1, page_size: int = 10):
        """List orders with pagination."""
        return self.repo.list_orders(page, page_size)

    def get_order(self, order_id: str):
        """Get a specific order."""
        return self.repo.get_order(order_id)
