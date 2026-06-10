from datetime import datetime, timedelta
from uuid import uuid4
from .models import ReservationState
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class IdempotencyKeyConflictError(Exception):
    pass


class CommerceService:
    RESERVATION_TTL_MINUTES = 30

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, stock_available: int):
        return self.repo.create_sku(sku_id, stock_available)

    def adjust_stock(self, sku_id: str, quantity_delta: int):
        sku = self.repo.get_sku(sku_id)
        if sku is None:
            raise ValueError(f"SKU {sku_id} not found")
        return self.repo.update_sku_stock(sku_id, quantity_delta)

    def create_reservation(
        self,
        sku_id: str,
        quantity: int,
        idempotency_key: str | None = None,
    ):
        # Check idempotency: if key provided and exists, return existing reservation
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.state == ReservationState.EXPIRED:
                    raise ReservationExpiredError(
                        f"Reservation {existing.reservation_id} has expired"
                    )
                return existing

        # Verify stock availability
        sku = self.repo.get_sku(sku_id)
        if sku is None:
            raise ValueError(f"SKU {sku_id} not found")
        if sku.stock_available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_id}: "
                f"requested {quantity}, available {sku.stock_available}"
            )

        # Reserve stock and create reservation
        self.repo.update_sku_stock(sku_id, -quantity)

        reservation_id = str(uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        return self.repo.create_reservation(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

    def confirm_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state == ReservationState.EXPIRED:
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.state != ReservationState.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in state {reservation.state}"
            )

        # Create order and update reservation state
        order_id = str(uuid4())
        self.repo.create_order(
            order_id=order_id,
            reservation_id=reservation_id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
        )

        return self.repo.update_reservation_state(
            reservation_id, ReservationState.CONFIRMED
        )

    def cancel_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state == ReservationState.CANCELLED:
            raise InvalidStateTransitionError(
                f"Reservation {reservation_id} is already cancelled"
            )

        if reservation.state == ReservationState.CONFIRMED:
            raise InvalidStateTransitionError(
                f"Cannot cancel confirmed reservation {reservation_id}"
            )

        # Release reserved stock
        self.repo.update_sku_stock(reservation.sku_id, reservation.quantity)

        return self.repo.update_reservation_state(
            reservation_id, ReservationState.CANCELLED
        )

    def get_order(self, order_id: str):
        order = self.repo.get_order(order_id)
        if order is None:
            raise ValueError(f"Order {order_id} not found")
        return order

    def list_orders(self, skip: int = 0, limit: int = 10):
        return self.repo.list_orders(skip, limit)

    def expire_pending_reservations(self):
        """Mark pending reservations as expired if past their TTL."""
        now = datetime.utcnow()
        expired = self.repo.list_expired_reservations(now)
        for reservation in expired:
            self.repo.update_reservation_state(
                reservation.reservation_id, ReservationState.EXPIRED
            )
            # Release reserved stock
            self.repo.update_sku_stock(reservation.sku_id, reservation.quantity)
        return expired
