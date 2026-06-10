"""Business logic service layer."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from commerce_service.repository import Repository
from commerce_service.models import (
    OrderResponse,
    OrderStatus,
    OrderItemResponse,
    ReservationResponse,
    SKUResponse,
)


class ServiceError(Exception):
    """Service layer exception."""
    pass


class InsufficientStockError(ServiceError):
    """Raised when requested quantity exceeds available stock."""
    pass


class ReservationNotFoundError(ServiceError):
    """Raised when reservation is not found."""
    pass


class ReservationExpiredError(ServiceError):
    """Raised when reservation has expired."""
    pass


class SKUNotFoundError(ServiceError):
    """Raised when SKU is not found."""
    pass


class CommerceService:
    """High-level commerce operations."""

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_code: str, name: str) -> SKUResponse:
        """Create a new SKU."""
        session = self.repo.get_session()
        try:
            sku = self.repo.create_sku(session, sku_code, name)
            return SKUResponse(
                id=sku.id,
                sku_code=sku.sku_code,
                name=sku.name,
                created_at=sku.created_at,
            )
        finally:
            session.close()

    def adjust_stock(self, sku_code: str, delta: int) -> dict:
        """Adjust inventory for a SKU."""
        session = self.repo.get_session()
        try:
            sku = self.repo.get_sku_by_code(session, sku_code)
            if not sku:
                raise SKUNotFoundError(f"SKU {sku_code} not found")

            stock = self.repo.adjust_stock(session, sku.id, delta)
            return {
                "sku_code": sku_code,
                "available": stock.available,
                "reserved": stock.reserved,
            }
        finally:
            session.close()

    def create_reservation(
        self, sku_code: str, quantity: int, idempotency_key: str
    ) -> ReservationResponse:
        """Create a reservation with idempotency."""
        session = self.repo.get_session()
        try:
            # Check if this idempotency key already exists
            existing = self.repo.get_reservation_by_idempotency_key(session, idempotency_key)
            if existing:
                # Return existing reservation if not expired
                if existing.status == "pending":
                    now = datetime.now(timezone.utc)
                    if existing.expires_at > now:
                        return self._reservation_to_response(existing)
                    else:
                        raise ReservationExpiredError("Existing reservation has expired")

            sku = self.repo.get_sku_by_code(session, sku_code)
            if not sku:
                raise SKUNotFoundError(f"SKU {sku_code} not found")

            # Try to reserve stock
            reserved = self.repo.reserve_stock(session, sku.id, quantity)
            if not reserved:
                raise InsufficientStockError(
                    f"Insufficient stock for {sku_code}: requested {quantity}"
                )

            # Create reservation record
            reservation = self.repo.create_reservation(session, sku.id, quantity, idempotency_key)
            return self._reservation_to_response(reservation)
        finally:
            session.close()

    def confirm_reservation(self, reservation_id: int) -> OrderResponse:
        """Confirm a reservation and create an order."""
        session = self.repo.get_session()
        try:
            reservation = self.repo.get_reservation(session, reservation_id)
            if not reservation:
                raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

            if reservation.status != "pending":
                raise ServiceError(f"Reservation is in {reservation.status} state")

            now = datetime.now(timezone.utc)
            if reservation.expires_at <= now:
                raise ReservationExpiredError("Reservation has expired")

            # Mark reservation as confirmed
            self.repo.update_reservation_status(session, reservation_id, "confirmed")

            # Create order with the reserved items
            order = self.repo.create_order(session)
            self.repo.create_order_item(session, order.id, reservation.sku_id, reservation.quantity)
            self.repo.update_order_status(session, order.id, "confirmed")

            # Clear the reservation from the reserved count
            self.repo.unreserve_stock(session, reservation.sku_id, reservation.quantity)

            return self._order_to_response(order, session)
        finally:
            session.close()

    def cancel_reservation(self, reservation_id: int) -> dict:
        """Cancel a reservation and release reserved stock."""
        session = self.repo.get_session()
        try:
            reservation = self.repo.get_reservation(session, reservation_id)
            if not reservation:
                raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

            if reservation.status != "pending":
                raise ServiceError(f"Cannot cancel reservation in {reservation.status} state")

            # Release reserved stock
            self.repo.unreserve_stock(session, reservation.sku_id, reservation.quantity)

            # Mark as cancelled
            self.repo.update_reservation_status(session, reservation_id, "cancelled")

            return {"reservation_id": reservation_id, "status": "cancelled"}
        finally:
            session.close()

    def list_orders(self, offset: int = 0, limit: int = 10) -> dict:
        """List orders with pagination."""
        session = self.repo.get_session()
        try:
            orders, total = self.repo.list_orders(session, offset, limit)
            return {
                "orders": [self._order_to_response(order, session) for order in orders],
                "total": total,
                "offset": offset,
                "limit": limit,
            }
        finally:
            session.close()

    def get_order(self, order_id: int) -> OrderResponse:
        """Get a specific order."""
        session = self.repo.get_session()
        try:
            order = self.repo.get_order(session, order_id)
            if not order:
                raise ServiceError(f"Order {order_id} not found")
            return self._order_to_response(order, session)
        finally:
            session.close()

    def cleanup_expired_reservations(self) -> int:
        """Clean up expired pending reservations."""
        session = self.repo.get_session()
        try:
            expired = self.repo.get_expired_reservations(session)
            count = 0
            for res in expired:
                self.repo.unreserve_stock(session, res.sku_id, res.quantity)
                self.repo.update_reservation_status(session, res.id, "cancelled")
                count += 1
            return count
        finally:
            session.close()

    def _reservation_to_response(self, reservation) -> ReservationResponse:
        """Convert reservation record to response."""
        return ReservationResponse(
            id=reservation.id,
            sku_code=None,  # Will be filled if needed
            quantity=reservation.quantity,
            status=reservation.status,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )

    def _order_to_response(self, order, session: Session) -> OrderResponse:
        """Convert order record to response."""
        items = self.repo.get_order_items(session, order.id)
        order_items = []
        for item in items:
            sku = self.repo.get_sku_by_id(session, item.sku_id)
            order_items.append(
                OrderItemResponse(
                    sku_code=sku.sku_code if sku else "UNKNOWN",
                    quantity=item.quantity,
                )
            )

        return OrderResponse(
            id=order.id,
            status=OrderStatus(order.status),
            items=order_items,
            created_at=order.created_at,
        )
