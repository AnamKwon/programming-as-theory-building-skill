import uuid
from datetime import datetime, timedelta
from typing import Optional

from commerce_service.models import OrderStatus, ReservationStatus
from commerce_service.repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class CommerceService:
    def __init__(self, repo: Repository, reservation_ttl_minutes: int = 30):
        self.repo = repo
        self.reservation_ttl = timedelta(minutes=reservation_ttl_minutes)

    def create_sku(self, sku_id: str, name: str, price: float):
        existing = self.repo.get_sku(sku_id)
        if existing:
            return existing

        sku = self.repo.create_sku(sku_id, name, price)
        self.repo.create_inventory(sku_id, available=0)
        self.repo.commit()
        return sku

    def get_sku(self, sku_id: str):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")
        return sku

    def list_skus(self):
        return self.repo.list_skus()

    def adjust_stock(self, sku_id: str, quantity_change: int):
        sku = self.get_sku(sku_id)
        inventory = self.repo.adjust_inventory(sku_id, quantity_change)
        if not inventory:
            raise SKUNotFoundError(f"Inventory for SKU {sku_id} not found")
        self.repo.commit()
        return inventory

    def get_inventory(self, sku_id: str):
        inventory = self.repo.get_inventory(sku_id)
        if not inventory:
            raise SKUNotFoundError(f"Inventory for SKU {sku_id} not found")
        return inventory

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: Optional[str] = None
    ):
        # Check idempotency: return existing reservation if key exists
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        # Validate SKU exists
        sku = self.get_sku(sku_id)

        # Check stock availability
        inventory = self.repo.get_inventory(sku_id)
        if not inventory or inventory.available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_id}. Available: {inventory.available if inventory else 0}, requested: {quantity}"
            )

        # Reserve inventory
        if not self.repo.reserve_inventory(sku_id, quantity):
            raise InsufficientStockError(f"Failed to reserve stock for SKU {sku_id}")

        # Create reservation
        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + self.reservation_ttl

        reservation = self.repo.create_reservation(
            reservation_id, sku_id, quantity, expires_at, idempotency_key
        )
        self.repo.commit()
        return reservation

    def get_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Check expiration
        if (
            reservation.status == ReservationStatus.PENDING
            and reservation.expires_at <= datetime.utcnow()
        ):
            # Expire the reservation
            self.repo.release_inventory(reservation.sku_id, reservation.quantity)
            self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
            self.repo.commit()
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        return reservation

    def confirm_reservation(self, reservation_id: str):
        reservation = self.get_reservation(reservation_id)

        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(
                f"Cannot confirm reservation in {reservation.status} status"
            )

        # Confirm inventory deduction
        if not self.repo.confirm_inventory(reservation.sku_id, reservation.quantity):
            raise InsufficientStockError(
                f"Failed to confirm inventory for reservation {reservation_id}"
            )

        # Update reservation status
        confirmed_at = datetime.utcnow()
        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED, confirmed_at
        )

        # Create order
        order_id = str(uuid.uuid4())
        self.repo.create_order(
            order_id,
            reservation.sku_id,
            reservation.quantity,
            reservation_id,
        )
        self.repo.update_order_status(order_id, OrderStatus.CONFIRMED, confirmed_at)

        self.repo.commit()
        return reservation

    def cancel_reservation(self, reservation_id: str):
        reservation = self.get_reservation(reservation_id)

        if reservation.status not in [ReservationStatus.PENDING, ReservationStatus.CONFIRMED]:
            raise ValueError(
                f"Cannot cancel reservation in {reservation.status} status"
            )

        # Release reserved inventory only if still PENDING
        if reservation.status == ReservationStatus.PENDING:
            self.repo.release_inventory(reservation.sku_id, reservation.quantity)

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
        self.repo.commit()
        return reservation

    def list_orders(self, skip: int = 0, limit: int = 20):
        orders, total = self.repo.list_orders(skip, limit)
        return orders, total
