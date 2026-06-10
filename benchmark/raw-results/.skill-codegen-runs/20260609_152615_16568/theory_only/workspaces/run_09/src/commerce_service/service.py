"""Business logic layer."""

import uuid
from datetime import datetime, timedelta, timezone

from .repository import ConflictError, NotFoundError, Repository, RepositoryError
from .models import OrderStatus


def utc_now_aware():
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


def make_aware(dt: datetime) -> datetime:
    """Convert a naive UTC datetime to timezone-aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class ServiceError(Exception):
    """Base service error."""


class InsufficientStockError(ServiceError):
    """Attempted to reserve more than available."""


class InvalidStateError(ServiceError):
    """Operation not allowed in current state."""


class ExpiredReservationError(ServiceError):
    """Reservation has expired."""


class Service:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repo: Repository):
        self.repo = repo

    # === SKU Management ===

    def create_sku(self, sku_id: str, name: str, initial_stock: int = 0) -> dict:
        """Create a new SKU and optionally set initial stock."""
        try:
            sku = self.repo.create_sku(sku_id, name)
        except ConflictError:
            raise ServiceError(f"SKU {sku_id} already exists")

        if initial_stock > 0:
            self.repo.initialize_stock(sku_id, initial_stock)

        self.repo.commit()
        return {"id": sku.id, "name": sku.name, "created_at": sku.created_at}

    def get_sku(self, sku_id: str) -> dict | None:
        sku = self.repo.get_sku(sku_id)
        return {"id": sku.id, "name": sku.name, "created_at": sku.created_at} if sku else None

    # === Stock Management ===

    def get_stock(self, sku_id: str) -> dict:
        """Get stock levels for a SKU."""
        stock = self.repo.get_stock(sku_id)
        if not stock:
            raise NotFoundError(f"No stock for SKU {sku_id}")
        return {
            "sku_id": stock.sku_id,
            "available": stock.available,
            "reserved": stock.reserved,
            "updated_at": stock.updated_at,
        }

    def adjust_stock(self, sku_id: str, quantity_delta: int) -> dict:
        """Adjust available inventory (business rule: admin operation)."""
        try:
            stock = self.repo.adjust_stock(sku_id, quantity_delta)
        except NotFoundError:
            raise ServiceError(f"SKU {sku_id} not initialized")

        self.repo.commit()
        return {
            "sku_id": stock.sku_id,
            "available": stock.available,
            "reserved": stock.reserved,
            "updated_at": stock.updated_at,
        }

    # === Reservation Management ===

    def create_reservation(
        self,
        sku_id: str,
        quantity: int,
        idempotency_key: str | None = None,
    ) -> dict:
        """Create a reservation if stock available."""
        if quantity <= 0:
            raise ServiceError("Quantity must be positive")

        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                if existing.status == OrderStatus.CANCELLED.value:
                    raise ServiceError("Idempotency key was previously cancelled")
                return {
                    "id": existing.id,
                    "sku_id": existing.sku_id,
                    "quantity": existing.quantity,
                    "status": existing.status,
                    "expires_at": existing.expires_at,
                    "created_at": existing.created_at,
                }

        stock = self.repo.get_stock(sku_id)
        if not stock or stock.available < quantity:
            raise InsufficientStockError(f"Only {stock.available if stock else 0} available for {sku_id}")

        reservation_id = str(uuid.uuid4())
        expires_at = utc_now_aware() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        try:
            self.repo.reserve_stock(sku_id, quantity)
            reservation = self.repo.create_reservation(
                reservation_id,
                sku_id,
                quantity,
                expires_at,
                idempotency_key,
            )
        except RepositoryError as e:
            self.repo.rollback()
            raise ServiceError(str(e))

        self.repo.commit()
        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

    def get_reservation(self, reservation_id: str) -> dict:
        """Get reservation details."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise NotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == OrderStatus.RESERVED.value:
            if utc_now_aware() > make_aware(reservation.expires_at):
                raise ExpiredReservationError(f"Reservation {reservation_id} expired")

        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

    def confirm_reservation(self, reservation_id: str) -> dict:
        """Confirm a reservation, creating an order."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise NotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status != OrderStatus.RESERVED.value:
            raise InvalidStateError(f"Cannot confirm reservation in {reservation.status} state")

        if utc_now_aware() > make_aware(reservation.expires_at):
            self.repo.update_reservation_status(reservation_id, OrderStatus.CANCELLED)
            self.repo.release_reserved_stock(reservation.sku_id, reservation.quantity)
            self.repo.commit()
            raise ExpiredReservationError("Reservation expired before confirmation")

        order_id = str(uuid.uuid4())
        try:
            self.repo.confirm_reserved_stock(reservation.sku_id, reservation.quantity)
            order = self.repo.create_order(
                order_id,
                reservation_id,
                reservation.sku_id,
                reservation.quantity,
            )
            self.repo.update_reservation_status(reservation_id, OrderStatus.CONFIRMED)
        except RepositoryError as e:
            self.repo.rollback()
            raise ServiceError(str(e))

        self.repo.commit()
        return {
            "id": order.id,
            "reservation_id": order.reservation_id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "status": order.status,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }

    def cancel_reservation(self, reservation_id: str) -> dict:
        """Cancel a reservation, releasing reserved stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise NotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == OrderStatus.CONFIRMED.value:
            raise InvalidStateError("Cannot cancel a confirmed order")

        if reservation.status == OrderStatus.CANCELLED.value:
            return {
                "id": reservation.id,
                "sku_id": reservation.sku_id,
                "quantity": reservation.quantity,
                "status": reservation.status,
                "expires_at": reservation.expires_at,
                "created_at": reservation.created_at,
            }

        try:
            self.repo.release_reserved_stock(reservation.sku_id, reservation.quantity)
            reservation = self.repo.update_reservation_status(reservation_id, OrderStatus.CANCELLED)
        except RepositoryError as e:
            self.repo.rollback()
            raise ServiceError(str(e))

        self.repo.commit()
        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

    # === Order Management ===

    def get_order(self, order_id: str) -> dict:
        """Get order details."""
        order = self.repo.get_order(order_id)
        if not order:
            raise NotFoundError(f"Order {order_id} not found")

        return {
            "id": order.id,
            "reservation_id": order.reservation_id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "status": order.status,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }

    def list_orders(self, page: int = 1, page_size: int = 10) -> dict:
        """List orders with pagination."""
        if page < 1 or page_size < 1:
            raise ServiceError("Page and page_size must be >= 1")

        skip = (page - 1) * page_size
        orders, total = self.repo.list_orders(skip, page_size)

        pages = (total + page_size - 1) // page_size

        return {
            "orders": [
                {
                    "id": o.id,
                    "reservation_id": o.reservation_id,
                    "sku_id": o.sku_id,
                    "quantity": o.quantity,
                    "status": o.status,
                    "created_at": o.created_at,
                    "updated_at": o.updated_at,
                }
                for o in orders
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": pages,
        }
