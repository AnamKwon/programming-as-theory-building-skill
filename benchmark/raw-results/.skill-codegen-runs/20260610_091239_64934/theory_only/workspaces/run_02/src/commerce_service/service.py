import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .models import Order, OrderStatus, Reservation, ReservationStatus, SKU
from .repository import OrderRepository, ReservationRepository, SKURepository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class OrderAlreadyExistsError(Exception):
    pass


class CommerceService:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, session: Session):
        self.session = session
        self.sku_repo = SKURepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.order_repo = OrderRepository(session)

    def create_sku(self, sku_id: str, name: str, initial_stock: int = 0) -> SKU:
        existing = self.sku_repo.get_by_id(sku_id)
        if existing:
            raise ValueError(f"SKU {sku_id} already exists")
        return self.sku_repo.create(sku_id, name, initial_stock)

    def adjust_stock(self, sku_id: str, quantity: int) -> SKU:
        sku = self.sku_repo.get_by_id(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return self.sku_repo.update_stock(sku_id, quantity)

    def create_reservation(
        self,
        sku_id: str,
        quantity: int,
        idempotency_key: str = None,
    ) -> Reservation:
        self._cleanup_expired_reservations()

        if idempotency_key:
            existing = self.reservation_repo.get_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        sku = self.sku_repo.get_by_id(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        if sku.available_stock < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_id}: "
                f"requested {quantity}, available {sku.available_stock}"
            )

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        reservation = self.reservation_repo.create(reservation_id, sku_id, quantity, expires_at)

        if idempotency_key:
            reservation.idempotency_key = idempotency_key
            self.session.commit()

        self.sku_repo.update_stock(sku_id, available_delta=-quantity, reserved_delta=quantity)

        return reservation

    def confirm_reservation(self, reservation_id: str) -> Order:
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.ACTIVE:
            raise ValueError(
                f"Reservation {reservation_id} is not active (status: {reservation.status})"
            )

        if datetime.utcnow() > reservation.expires_at:
            self.reservation_repo.update_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        self.reservation_repo.update_status(reservation_id, ReservationStatus.CONFIRMED)

        order_id = str(uuid.uuid4())
        order = self.order_repo.create(
            order_id,
            reservation.sku_id,
            reservation.quantity,
            reservation_id=reservation_id,
        )

        self.order_repo.update_status(order_id, OrderStatus.CONFIRMED)

        return order

    def cancel_reservation(self, reservation_id: str) -> Reservation:
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.ACTIVE:
            raise ValueError(
                f"Cannot cancel reservation {reservation_id} with status {reservation.status}"
            )

        self.reservation_repo.update_status(reservation_id, ReservationStatus.CANCELLED)

        sku = self.sku_repo.get_by_id(reservation.sku_id)
        if sku:
            self.sku_repo.update_stock(
                reservation.sku_id,
                available_delta=reservation.quantity,
                reserved_delta=-reservation.quantity,
            )

        return reservation

    def get_order(self, order_id: str) -> Order:
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return order

    def list_orders(self, offset: int = 0, limit: int = 10) -> tuple[list[Order], int]:
        return self.order_repo.list_orders(offset, limit)

    def _cleanup_expired_reservations(self):
        expired = self.reservation_repo.get_expired()
        for reservation in expired:
            self.reservation_repo.update_status(reservation.id, ReservationStatus.EXPIRED)
            sku = self.sku_repo.get_by_id(reservation.sku_id)
            if sku:
                self.sku_repo.update_stock(
                    reservation.sku_id,
                    available_delta=reservation.quantity,
                    reserved_delta=-reservation.quantity,
                )
