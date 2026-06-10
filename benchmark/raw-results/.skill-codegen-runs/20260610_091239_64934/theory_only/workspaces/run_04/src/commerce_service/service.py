from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .models import OrderStatus, ReservationStatus
from .repository import Repository


class ServiceError(Exception):
    pass


class InsufficientStockError(ServiceError):
    pass


class ReservationNotFoundError(ServiceError):
    pass


class ReservationExpiredError(ServiceError):
    pass


class InvalidStateTransitionError(ServiceError):
    pass


class IdempotencyViolationError(ServiceError):
    pass


class CommerceService:
    def __init__(self, db: Session):
        self.repo = Repository(db)
        self.db = db

    def create_sku(self, sku: str, name: str, base_price: float):
        """Create a new SKU."""
        existing = self.repo.get_sku_by_code(sku)
        if existing:
            raise ServiceError(f"SKU {sku} already exists")
        return self.repo.create_sku(sku, name, base_price)

    def adjust_stock(self, sku_id: int, quantity_delta: int):
        """Adjust stock level. Can be positive or negative."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ServiceError(f"SKU {sku_id} not found")

        stock = self.repo.adjust_stock(sku_id, quantity_delta)
        if stock.quantity < 0:
            raise ServiceError("Stock cannot be negative")
        return stock

    def get_stock(self, sku_id: int):
        """Get current stock level."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ServiceError(f"SKU {sku_id} not found")
        stock = self.repo.get_stock(sku_id)
        if not stock:
            stock = self.repo.get_or_create_stock(sku_id)
        return stock

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        ttl_seconds: int = 3600,
        idempotency_key: str | None = None,
    ):
        """Create a reservation for a SKU. Returns reservation or (existing, True) if idempotent."""
        # Check SKU exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ServiceError(f"SKU {sku_id} not found")

        # Idempotency check: same key returns same reservation
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                if existing.sku_id != sku_id or existing.quantity != quantity:
                    raise IdempotencyViolationError(
                        "Idempotency key used with different parameters"
                    )
                return existing, True

        # Check stock availability
        stock = self.repo.get_stock(sku_id)
        available = (stock.quantity if stock else 0) - self._get_pending_reserved(sku_id)

        if available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock. Available: {available}, Requested: {quantity}"
            )

        # Create reservation
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        reservation = self.repo.create_reservation(
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

        # Create order for the reservation
        self.repo.create_order(reservation.id, quantity)

        return reservation, False

    def confirm_reservation(self, reservation_id: int):
        """Confirm a pending reservation, transitioning it to confirmed state."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CONFIRMED:
            return reservation

        if reservation.status != ReservationStatus.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in {reservation.status} state"
            )

        # Check if expired
        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(
                reservation_id, ReservationStatus.EXPIRED
            )
            raise ReservationExpiredError(
                f"Reservation {reservation_id} has expired"
            )

        # Confirm both reservation and order
        updated = self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED
        )
        order = self.repo.get_order_by_reservation(reservation_id)
        if order:
            self.repo.update_order_status(order.id, OrderStatus.CONFIRMED)

        return updated

    def cancel_reservation(self, reservation_id: int):
        """Cancel a reservation, releasing the reserved stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CANCELLED:
            return reservation

        if reservation.status == ReservationStatus.CONFIRMED:
            raise InvalidStateTransitionError(
                "Cannot cancel a confirmed reservation"
            )

        # Cancel both reservation and order
        updated = self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED
        )
        order = self.repo.get_order_by_reservation(reservation_id)
        if order:
            self.repo.update_order_status(order.id, OrderStatus.CANCELLED)

        return updated

    def get_reservation(self, reservation_id: int):
        """Get reservation details."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")
        return reservation

    def list_orders(self, page: int = 1, page_size: int = 10):
        """List orders with pagination."""
        orders, total = self.repo.list_orders(page, page_size)
        return orders, total

    def get_order(self, order_id: int):
        """Get order details."""
        order = self.repo.get_order(order_id)
        if not order:
            raise ServiceError(f"Order {order_id} not found")
        return order

    def _get_pending_reserved(self, sku_id: int) -> int:
        """Get total quantity reserved (pending) for a SKU."""
        reservations = self.repo.get_pending_reservations_by_sku(sku_id)
        return sum(r.quantity for r in reservations)
