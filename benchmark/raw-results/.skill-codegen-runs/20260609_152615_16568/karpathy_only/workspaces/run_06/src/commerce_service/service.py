import uuid
from datetime import datetime, timedelta

from .models import ReservationStatus, OrderStatus
from .repository import Repository


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


class Service:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku_code: str, name: str, initial_stock: int):
        return self.repo.create_sku(sku_code, name, initial_stock)

    def adjust_stock(self, sku_id: int, quantity: int):
        return self.repo.adjust_sku_stock(sku_id, quantity)

    def create_reservation(
        self, idempotency_key: str, items: list[tuple[int, int]], expiry_minutes: int
    ):
        # Check for idempotent retry
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == ReservationStatus.EXPIRED:
                raise ReservationExpiredError(
                    f"Reservation {existing.reservation_id} has expired"
                )
            return existing

        # Verify stock availability
        for sku_id, quantity in items:
            sku = self.repo.get_sku(sku_id)
            if not sku:
                raise ValueError(f"SKU {sku_id} not found")
            if sku.stock_quantity < quantity:
                raise InsufficientStockError(
                    f"SKU {sku_id} has {sku.stock_quantity} available, "
                    f"but {quantity} requested"
                )

        # Reserve stock
        for sku_id, quantity in items:
            self.repo.adjust_sku_stock(sku_id, -quantity)

        # Create reservation
        reservation_id = f"res-{uuid.uuid4().hex[:12]}"
        expires_at = datetime.utcnow() + timedelta(minutes=expiry_minutes)

        reservation = self.repo.create_reservation(
            reservation_id, idempotency_key, expires_at, items
        )
        self.repo.commit()

        return reservation

    def confirm_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation_by_public_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if datetime.utcnow() > reservation.expires_at:
            self._expire_reservation(reservation)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.status != ReservationStatus.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in {reservation.status} status"
            )

        # Create order from reservation
        order_id = f"ord-{uuid.uuid4().hex[:12]}"
        order = self.repo.create_order(order_id, reservation.id)

        # Update reservation status
        self.repo.update_reservation_status(reservation.id, ReservationStatus.CONFIRMED)
        self.repo.update_order_status(order.id, OrderStatus.CONFIRMED)

        self.repo.commit()
        return order

    def cancel_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation_by_public_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status not in [
            ReservationStatus.PENDING,
            ReservationStatus.EXPIRED,
        ]:
            raise InvalidStateTransitionError(
                f"Cannot cancel reservation in {reservation.status} status"
            )

        # Release reserved stock
        for item in reservation.items:
            self.repo.adjust_sku_stock(item.sku_id, item.quantity)

        self.repo.update_reservation_status(reservation.id, ReservationStatus.CANCELLED)
        self.repo.commit()

        return reservation

    def get_order(self, order_id: str):
        order = self.repo.get_order_by_public_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return order

    def list_orders(self, skip: int = 0, limit: int = 10):
        return self.repo.list_orders(skip, limit)

    def _expire_reservation(self, reservation):
        if reservation.status == ReservationStatus.PENDING:
            # Release reserved stock
            for item in reservation.items:
                self.repo.adjust_sku_stock(item.sku_id, item.quantity)
            self.repo.update_reservation_status(reservation.id, ReservationStatus.EXPIRED)
            self.repo.commit()
