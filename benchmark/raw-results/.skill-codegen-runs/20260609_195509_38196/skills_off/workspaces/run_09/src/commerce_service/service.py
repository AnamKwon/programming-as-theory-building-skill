from datetime import datetime, timedelta, timezone

from .models import OrderStatus, ReservationStatus
from .repository import Repository


def make_aware(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware, defaulting to UTC if naive."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class StockUnavailable(Exception):
    pass


class ReservationExpired(Exception):
    pass


class ReservationNotFound(Exception):
    pass


class SKUNotFound(Exception):
    pass


class CommercService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku_code: str, initial_stock: int = 0):
        existing = self.repo.get_sku_by_code(sku_code)
        if existing:
            raise ValueError(f"SKU with code {sku_code} already exists")
        return self.repo.create_sku(sku_code, initial_stock)

    def adjust_stock(self, sku_id: int, adjustment: int):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFound(f"SKU {sku_id} not found")

        new_stock = sku.current_stock + adjustment
        if new_stock < 0:
            raise ValueError("Adjustment would result in negative stock")

        return self.repo.update_sku_stock(sku_id, new_stock, sku.reserved_count)

    def reserve_inventory(
        self, sku_id: int, quantity: int, idempotency_key: str, ttl_seconds: int = 300
    ):
        # Check for idempotency: return existing reservation if already created
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == ReservationStatus.CANCELLED:
                raise ValueError(
                    f"Idempotency key {idempotency_key} was previously used for a cancelled reservation"
                )
            return existing

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFound(f"SKU {sku_id} not found")

        # Check available stock (current_stock minus already reserved)
        available = sku.current_stock - sku.reserved_count
        if available < quantity:
            raise StockUnavailable(
                f"Insufficient stock: requested {quantity}, available {available}"
            )

        # Create reservation
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        reservation = self.repo.create_reservation(sku_id, quantity, idempotency_key, expires_at)

        # Reserve stock
        new_reserved = sku.reserved_count + quantity
        self.repo.update_sku_stock(sku_id, sku.current_stock, new_reserved)

        return reservation

    def confirm_reservation(self, reservation_id: int):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFound(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CANCELLED:
            raise ValueError("Cannot confirm a cancelled reservation")

        if reservation.status == ReservationStatus.CONFIRMED:
            # Idempotent: already confirmed
            sku = self.repo.get_sku(reservation.sku_id)
            orders = self.repo.db.query(__import__('sqlalchemy').orm.Session).first()
            # Return existing order if it exists
            from .models import OrderModel
            order = (
                self.repo.db.query(OrderModel)
                .filter(OrderModel.reservation_id == reservation_id)
                .first()
            )
            if order:
                return reservation, order
            # Should not happen, but create if missing
            order = self.repo.create_order(reservation.sku_id, reservation.quantity, reservation_id)
            self.repo.update_order_status(order.id, OrderStatus.CONFIRMED)
            return reservation, order

        # Check expiration
        now = datetime.now(timezone.utc)
        expires_at = make_aware(reservation.expires_at)
        if now > expires_at:
            raise ReservationExpired(f"Reservation {reservation_id} has expired")

        # Confirm reservation
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

        # Deduct from available stock and create order
        sku = self.repo.get_sku(reservation.sku_id)
        new_current = sku.current_stock - reservation.quantity
        new_reserved = sku.reserved_count - reservation.quantity
        self.repo.update_sku_stock(reservation.sku_id, new_current, new_reserved)

        order = self.repo.create_order(reservation.sku_id, reservation.quantity, reservation_id)
        self.repo.update_order_status(order.id, OrderStatus.CONFIRMED)

        return reservation, order

    def cancel_reservation(self, reservation_id: int):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFound(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CANCELLED:
            # Idempotent: already cancelled
            return reservation

        if reservation.status == ReservationStatus.CONFIRMED:
            raise ValueError("Cannot cancel a confirmed reservation")

        # Release reserved stock
        sku = self.repo.get_sku(reservation.sku_id)
        new_reserved = sku.reserved_count - reservation.quantity
        self.repo.update_sku_stock(reservation.sku_id, sku.current_stock, new_reserved)

        # Cancel reservation
        return self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

    def list_orders(self, skip: int = 0, limit: int = 10):
        return self.repo.list_orders(skip, limit)
