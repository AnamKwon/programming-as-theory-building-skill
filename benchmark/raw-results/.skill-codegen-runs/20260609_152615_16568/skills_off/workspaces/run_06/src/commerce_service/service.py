"""Business logic and service layer."""

from datetime import datetime, timedelta

from .models import OrderStatus, ReservationStatus
from .repository import Repository


class InsufficientStockError(Exception):
    """Raised when there is not enough stock to fulfill a reservation."""

    pass


class ReservationNotFoundError(Exception):
    """Raised when a reservation cannot be found."""

    pass


class ReservationExpiredError(Exception):
    """Raised when a reservation has expired."""

    pass


class ReservationAlreadyConfirmedError(Exception):
    """Raised when trying to operate on an already-confirmed reservation."""

    pass


class CommerceService:
    """Service layer for commerce operations."""

    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku: str, stock_qty: int) -> dict:
        """Create a new SKU with initial stock."""
        return self.repo.create_sku(sku, stock_qty)

    def adjust_stock(self, sku: str, delta: int) -> dict:
        """Adjust stock quantity for a SKU."""
        sku_record = self.repo.get_sku_by_code(sku)
        if not sku_record:
            raise ValueError(f"SKU not found: {sku}")

        new_qty = sku_record["stock_qty"] + delta
        if new_qty < 0:
            raise ValueError(f"Stock cannot be negative: {new_qty}")

        return self.repo.adjust_stock(sku, delta)

    def reserve_inventory(self, sku: str, qty: int, idempotency_key: str) -> dict:
        """Reserve inventory with idempotency guarantees.

        If the same idempotency key is used, return the existing reservation
        instead of creating a duplicate. Reserves stock immediately on first call.
        """
        # Check for existing reservation with this idempotency key
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing["status"] == ReservationStatus.EXPIRED.value:
                raise ReservationExpiredError("Previous reservation with this key has expired")
            return existing

        # Validate SKU exists and has sufficient stock
        sku_record = self.repo.get_sku_by_code(sku)
        if not sku_record:
            raise ValueError(f"SKU not found: {sku}")

        if sku_record["stock_qty"] < qty:
            raise InsufficientStockError(
                f"Insufficient stock for {sku}: requested {qty}, available {sku_record['stock_qty']}"
            )

        # Reserve stock
        expires_at = datetime.now() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)
        self.repo.adjust_stock(sku, -qty)

        return self.repo.create_reservation(sku, qty, idempotency_key, expires_at)

    def confirm_reservation(self, reservation_id: int) -> dict:
        """Confirm a reservation and create an order."""
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation not found: {reservation_id}")

        if reservation["status"] == ReservationStatus.CONFIRMED.value:
            raise ReservationAlreadyConfirmedError(f"Reservation already confirmed: {reservation_id}")

        if reservation["status"] == ReservationStatus.CANCELLED.value:
            raise ValueError(f"Cannot confirm cancelled reservation: {reservation_id}")

        # Check expiration
        expires_at = datetime.fromisoformat(reservation["expires_at"])
        if datetime.now() > expires_at:
            self.repo.update_reservation_status(
                reservation_id, ReservationStatus.EXPIRED.value
            )
            raise ReservationExpiredError(f"Reservation has expired: {reservation_id}")

        # Create order and mark reservation confirmed
        order = self.repo.create_order(
            reservation_id, reservation["sku"], reservation["qty"]
        )
        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED.value
        )

        return order

    def cancel_reservation(self, reservation_id: int) -> dict:
        """Cancel a reservation and release reserved stock."""
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation not found: {reservation_id}")

        status = reservation["status"]
        if status == ReservationStatus.CANCELLED.value:
            raise ValueError(f"Reservation already cancelled: {reservation_id}")

        if status == ReservationStatus.CONFIRMED.value:
            raise ValueError(f"Cannot cancel confirmed reservation: {reservation_id}")

        # Release reserved stock
        self.repo.adjust_stock(reservation["sku"], reservation["qty"])
        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED.value
        )

        return self.repo.get_reservation_by_id(reservation_id)

    def get_orders(self, page: int = 1, page_size: int = 20) -> dict:
        """Get paginated list of orders."""
        if page < 1:
            raise ValueError("Page must be >= 1")
        if page_size < 1 or page_size > 100:
            raise ValueError("Page size must be between 1 and 100")

        orders, total = self.repo.get_orders(page, page_size)
        total_pages = (total + page_size - 1) // page_size

        return {
            "items": orders,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
