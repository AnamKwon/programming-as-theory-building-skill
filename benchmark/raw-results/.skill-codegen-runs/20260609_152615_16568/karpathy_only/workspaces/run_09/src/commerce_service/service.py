import uuid
from datetime import datetime, timedelta, timezone

from .models import OrderStatus, ReservationStatus
from .repository import Repository


class ServiceError(Exception):
    pass


class ConflictError(ServiceError):
    pass


class NotFoundError(ServiceError):
    pass


class InsufficientStockError(ServiceError):
    pass


class InvalidStateError(ServiceError):
    pass


class CommerceService:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repository: Repository):
        self.repo = repository

    # SKU operations

    def create_sku(self, sku_code: str, description: str | None) -> dict:
        existing = self.repo.get_sku(sku_code)
        if existing:
            raise ConflictError(f"SKU {sku_code} already exists")

        sku = self.repo.create_sku(sku_code, description)
        self.repo.create_stock(sku_code, quantity=0)
        return {"sku_code": sku.sku_code, "description": sku.description, "created_at": sku.created_at}

    def adjust_stock(self, sku_code: str, quantity_delta: int) -> dict:
        sku = self.repo.get_sku(sku_code)
        if not sku:
            raise NotFoundError(f"SKU {sku_code} not found")

        self.repo.update_stock(sku_code, quantity_delta)
        stock = self.repo.get_stock(sku_code)
        return {
            "sku_code": stock.sku_code,
            "quantity": stock.quantity,
            "reserved_quantity": stock.reserved_quantity,
        }

    # Reservation operations

    def create_reservation(self, sku_code: str, quantity: int, idempotency_key: str) -> dict:
        sku = self.repo.get_sku(sku_code)
        if not sku:
            raise NotFoundError(f"SKU {sku_code} not found")

        # Check for idempotency
        existing = self.repo.get_reservation_by_idempotency_key(sku_code, idempotency_key)
        if existing:
            if existing.status == ReservationStatus.EXPIRED:
                raise ConflictError("A prior reservation for this idempotency key has expired")
            if existing.status == ReservationStatus.CANCELLED:
                raise ConflictError("A prior reservation for this idempotency key has been cancelled")
            # Return the existing pending or confirmed reservation
            return self._reservation_to_dict(existing)

        # Check availability
        stock = self.repo.get_stock(sku_code)
        if not stock or stock.quantity < quantity:
            raise InsufficientStockError(f"Insufficient stock for SKU {sku_code}")

        # Create reservation and reserve stock
        reservation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        reservation = self.repo.create_reservation(reservation_id, sku_code, quantity, idempotency_key, expires_at)
        self.repo.reserve_stock(sku_code, quantity)

        return self._reservation_to_dict(reservation)

    def confirm_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise NotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.EXPIRED:
            raise InvalidStateError("Cannot confirm an expired reservation")
        if reservation.status == ReservationStatus.CANCELLED:
            raise InvalidStateError("Cannot confirm a cancelled reservation")
        if reservation.status == ReservationStatus.CONFIRMED:
            return self._reservation_to_dict(reservation)

        # Verify reservation is not expired
        now = datetime.now(timezone.utc)
        if now >= reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            self.repo.release_reservation(reservation.sku_code, reservation.quantity)
            raise InvalidStateError("Reservation has expired")

        # Confirm reservation: deduct stock and mark confirmed
        self.repo.confirm_reservation_stock(reservation.sku_code, reservation.quantity)
        now = datetime.now(timezone.utc)
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED, confirmed_at=now)

        # Create order
        order_id = str(uuid.uuid4())
        self.repo.create_order(order_id, reservation.sku_code, reservation.quantity, reservation_id)

        reservation = self.repo.get_reservation(reservation_id)
        return self._reservation_to_dict(reservation)

    def cancel_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise NotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CANCELLED:
            return self._reservation_to_dict(reservation)
        if reservation.status == ReservationStatus.CONFIRMED:
            raise InvalidStateError("Cannot cancel a confirmed reservation")
        if reservation.status == ReservationStatus.EXPIRED:
            raise InvalidStateError("Cannot cancel an expired reservation")

        # Release the reservation
        self.repo.release_reservation(reservation.sku_code, reservation.quantity)
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

        reservation = self.repo.get_reservation(reservation_id)
        return self._reservation_to_dict(reservation)

    # Order operations

    def get_order(self, order_id: str) -> dict:
        order = self.repo.get_order(order_id)
        if not order:
            raise NotFoundError(f"Order {order_id} not found")
        return self._order_to_dict(order)

    def get_orders(self, page: int = 1, page_size: int = 20) -> dict:
        orders, total = self.repo.get_orders_paginated(page, page_size)
        return {
            "orders": [self._order_to_dict(o) for o in orders],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # Expiration management

    def expire_pending_reservations(self):
        now = datetime.now(timezone.utc)
        expired = self.repo.get_expired_reservations(now)
        for reservation in expired:
            self.repo.update_reservation_status(reservation.reservation_id, ReservationStatus.EXPIRED)
            self.repo.release_reservation(reservation.sku_code, reservation.quantity)
        return len(expired)

    # Helpers

    def _reservation_to_dict(self, reservation) -> dict:
        return {
            "reservation_id": reservation.reservation_id,
            "sku_code": reservation.sku_code,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
            "confirmed_at": reservation.confirmed_at,
        }

    def _order_to_dict(self, order) -> dict:
        return {
            "order_id": order.order_id,
            "sku_code": order.sku_code,
            "quantity": order.quantity,
            "status": order.status,
            "created_at": order.created_at,
        }
