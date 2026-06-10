from datetime import datetime, timedelta
from uuid import uuid4

from .models import ReservationStatus
from .repository import Repository, RepositoryError


class ServiceError(Exception):
    pass


class InsufficientStockError(ServiceError):
    pass


class ReservationNotFoundError(ServiceError):
    pass


class ReservationExpiredError(ServiceError):
    pass


class Service:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, name: str, initial_stock: int):
        try:
            return self.repo.create_sku(sku, name, initial_stock)
        except RepositoryError as e:
            raise ServiceError(str(e))

    def adjust_stock(self, sku: str, quantity: int):
        try:
            db_sku = self.repo.get_sku(sku)
            if not db_sku:
                raise ServiceError(f"SKU {sku} not found")
            if db_sku.total_stock + quantity < 0:
                raise InsufficientStockError("Stock adjustment would result in negative inventory")
            self.repo.update_sku_stock(sku, quantity)
        except RepositoryError as e:
            raise ServiceError(str(e))

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str):
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == ReservationStatus.EXPIRED:
                raise ReservationExpiredError("Reservation has expired")
            return existing

        db_sku = self.repo.get_sku(sku)
        if not db_sku:
            raise ServiceError(f"SKU {sku} not found")

        available = db_sku.total_stock - db_sku.reserved_stock
        if available < quantity:
            raise InsufficientStockError(f"Insufficient stock: {available} available, {quantity} requested")

        reservation_id = str(uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        try:
            reservation = self.repo.create_reservation(
                reservation_id, sku, quantity, expires_at, idempotency_key
            )
            db_sku.reserved_stock += quantity
            self.repo.session.commit()
            return reservation
        except RepositoryError as e:
            raise ServiceError(str(e))

    def confirm_reservation(self, reservation_id: str, idempotency_key: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.EXPIRED:
            raise ReservationExpiredError("Reservation has expired")

        if reservation.status == ReservationStatus.CANCELLED:
            raise ServiceError("Reservation has been cancelled")

        if reservation.status == ReservationStatus.CONFIRMED:
            existing_order = self.repo.get_order(reservation.reservation_id)
            if existing_order:
                return existing_order
            raise ServiceError("Reservation already confirmed but order not found")

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            db_sku = self.repo.get_sku(reservation.sku)
            if db_sku:
                db_sku.reserved_stock -= reservation.quantity
            self.repo.session.commit()
            raise ReservationExpiredError("Reservation has expired")

        order_id = str(uuid4())
        order = self.repo.create_order(order_id, reservation.sku, reservation.quantity, reservation_id)
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

        return order

    def cancel_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status in (ReservationStatus.CONFIRMED, ReservationStatus.CANCELLED, ReservationStatus.EXPIRED):
            raise ServiceError(f"Cannot cancel reservation in {reservation.status} state")

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
        db_sku = self.repo.get_sku(reservation.sku)
        if db_sku:
            db_sku.reserved_stock -= reservation.quantity
        self.repo.session.commit()

    def get_order(self, order_id: str):
        order = self.repo.get_order(order_id)
        if not order:
            raise ServiceError(f"Order {order_id} not found")
        return order

    def list_orders(self, page: int = 1, page_size: int = 10):
        if page < 1 or page_size < 1:
            raise ServiceError("Page and page_size must be >= 1")
        return self.repo.list_orders(page, page_size)

    def get_sku(self, sku: str):
        db_sku = self.repo.get_sku(sku)
        if not db_sku:
            raise ServiceError(f"SKU {sku} not found")
        return db_sku
