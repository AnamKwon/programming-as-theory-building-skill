from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .models import OrderModel, OrderStatus, ReservationModel, ReservationStatus
from .repository import OrderRepository, ReservationRepository, SKURepository


class SKUAlreadyExistsError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class DuplicateReservationError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class CommercService:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, session: Session):
        self.session = session
        self.sku_repo = SKURepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.order_repo = OrderRepository(session)

    def create_sku(self, sku_code: str, name: str, stock: int) -> dict:
        """Create a new SKU with initial stock."""
        existing = self.sku_repo.get_by_code(sku_code)
        if existing:
            raise SKUAlreadyExistsError(f"SKU already exists: {sku_code}")

        sku = self.sku_repo.create(sku_code, name, stock)
        return {
            "sku": sku.sku,
            "name": sku.name,
            "stock": sku.stock,
            "reserved": 0,
        }

    def get_sku(self, sku_code: str) -> dict:
        """Get SKU with current stock and reserved quantities."""
        sku = self.sku_repo.get_by_code(sku_code)
        if not sku:
            raise SKUNotFoundError(f"SKU not found: {sku_code}")

        reserved = sum(
            r.quantity
            for r in sku.reservations
            if r.status in (ReservationStatus.PENDING, ReservationStatus.CONFIRMED)
        )

        return {
            "sku": sku.sku,
            "name": sku.name,
            "stock": sku.stock,
            "reserved": reserved,
        }

    def adjust_stock(self, sku_code: str, delta: int) -> dict:
        """Adjust stock by delta amount."""
        sku = self.sku_repo.get_by_code(sku_code)
        if not sku:
            raise SKUNotFoundError(f"SKU not found: {sku_code}")

        sku = self.sku_repo.adjust_stock(sku_code, delta)
        reserved = sum(
            r.quantity
            for r in sku.reservations
            if r.status in (ReservationStatus.PENDING, ReservationStatus.CONFIRMED)
        )

        return {
            "sku": sku.sku,
            "name": sku.name,
            "stock": sku.stock,
            "reserved": reserved,
        }

    def create_reservation(
        self, sku_code: str, quantity: int, idempotency_key: str
    ) -> dict:
        """Create a reservation for a SKU with idempotency."""
        # Check for idempotent retry
        existing = self.reservation_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            if existing.is_expired():
                raise ReservationExpiredError("Reservation has expired")
            return self._format_reservation(existing)

        # Get SKU and validate stock
        sku = self.sku_repo.get_by_code(sku_code)
        if not sku:
            raise SKUNotFoundError(f"SKU not found: {sku_code}")

        available = sku.available_stock()
        if available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock: have {available}, need {quantity}"
            )

        # Create reservation
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)
        reservation = self.reservation_repo.create(
            sku_id=sku.id,
            sku_code=sku_code,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )

        return self._format_reservation(reservation)

    def confirm_reservation(self, reservation_id: int) -> dict:
        """Confirm a pending reservation."""
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation not found: {reservation_id}")

        if reservation.is_expired():
            self.reservation_repo.update_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError("Reservation has expired")

        if reservation.status != ReservationStatus.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in {reservation.status} state"
            )

        reservation = self.reservation_repo.update_status(
            reservation_id, ReservationStatus.CONFIRMED
        )

        # Create order for confirmed reservation
        self.order_repo.create(
            reservation_id=reservation.id,
            sku=reservation.sku_code,
            quantity=reservation.quantity,
            status=OrderStatus.CONFIRMED,
        )

        return self._format_reservation(reservation)

    def cancel_reservation(self, reservation_id: int) -> dict:
        """Cancel a reservation."""
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation not found: {reservation_id}")

        if reservation.status not in (
            ReservationStatus.PENDING,
            ReservationStatus.CONFIRMED,
        ):
            raise InvalidStateTransitionError(
                f"Cannot cancel reservation in {reservation.status} state"
            )

        reservation = self.reservation_repo.update_status(
            reservation_id, ReservationStatus.CANCELLED
        )

        return self._format_reservation(reservation)

    def list_orders(self, offset: int = 0, limit: int = 50) -> dict:
        """List orders with pagination."""
        orders, total = self.order_repo.list_orders(offset=offset, limit=limit)
        return {
            "orders": [self._format_order(order) for order in orders],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    def get_order(self, order_id: int) -> dict:
        """Get a single order by ID."""
        order = self.session.query(OrderModel).filter(OrderModel.id == order_id).first()
        if not order:
            raise Exception(f"Order not found: {order_id}")
        return self._format_order(order)

    @staticmethod
    def _format_reservation(reservation: ReservationModel) -> dict:
        return {
            "reservation_id": reservation.id,
            "sku": reservation.sku_code,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
        }

    @staticmethod
    def _format_order(order: OrderModel) -> dict:
        return {
            "order_id": order.id,
            "sku": order.sku,
            "quantity": order.quantity,
            "status": order.status,
            "created_at": order.created_at,
        }
