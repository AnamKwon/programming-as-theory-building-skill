import uuid
from datetime import datetime, timedelta

from .models import ReservationStatus
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ConflictError(Exception):
    pass


class ServiceError(Exception):
    pass


class CommercialService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, name: str, description: str | None) -> dict:
        sku = self.repo.create_sku(sku_id, name, description)
        return {
            "id": sku.id,
            "name": sku.name,
            "description": sku.description,
            "created_at": sku.created_at,
        }

    def adjust_stock(self, sku_id: str, quantity_delta: int) -> dict:
        stock = self.repo.get_stock(sku_id)
        if not stock:
            raise ServiceError(f"Stock not found for SKU {sku_id}")

        stock = self.repo.adjust_stock(sku_id, quantity_delta)
        return {
            "sku_id": stock.sku_id,
            "quantity": stock.quantity,
            "updated_at": stock.updated_at,
        }

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str, reservation_ttl_seconds: int
    ) -> dict:
        self.repo.mark_expired_reservations()

        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == ReservationStatus.EXPIRED:
                raise ConflictError("Idempotency key previously resulted in expired reservation")
            if existing.status == ReservationStatus.CANCELLED:
                raise ConflictError("Idempotency key previously resulted in cancelled reservation")
            return {
                "id": existing.id,
                "sku_id": existing.sku_id,
                "quantity": existing.quantity,
                "status": existing.status,
                "idempotency_key": existing.idempotency_key,
                "created_at": existing.created_at,
                "expires_at": existing.expires_at,
                "confirmed_at": existing.confirmed_at,
            }

        stock = self.repo.get_stock(sku_id)
        if not stock:
            raise ServiceError(f"SKU {sku_id} not found")

        if stock.quantity < quantity:
            raise InsufficientStockError(
                f"Insufficient stock. Available: {stock.quantity}, Requested: {quantity}"
            )

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(seconds=reservation_ttl_seconds)

        reservation = self.repo.create_reservation(
            reservation_id, sku_id, quantity, idempotency_key, expires_at
        )

        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "idempotency_key": reservation.idempotency_key,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
            "confirmed_at": reservation.confirmed_at,
        }

    def confirm_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.PENDING:
            raise ConflictError(f"Reservation is {reservation.status}, cannot confirm")

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        confirmed_at = datetime.utcnow()
        reservation = self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED, confirmed_at
        )

        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "idempotency_key": reservation.idempotency_key,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
            "confirmed_at": reservation.confirmed_at,
        }

    def cancel_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        reservation = self.repo.cancel_reservation(reservation_id)
        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "idempotency_key": reservation.idempotency_key,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
            "confirmed_at": reservation.confirmed_at,
        }

    def get_order(self, order_id: str) -> dict:
        order = self.repo.get_order(order_id)
        if not order:
            raise ServiceError(f"Order {order_id} not found")

        reservations = [
            {
                "id": or_assoc.reservation.id,
                "sku_id": or_assoc.reservation.sku_id,
                "quantity": or_assoc.reservation.quantity,
                "status": or_assoc.reservation.status,
                "idempotency_key": or_assoc.reservation.idempotency_key,
                "created_at": or_assoc.reservation.created_at,
                "expires_at": or_assoc.reservation.expires_at,
                "confirmed_at": or_assoc.reservation.confirmed_at,
            }
            for or_assoc in order.order_reservations
        ]

        return {
            "id": order.id,
            "status": order.status,
            "reservations": reservations,
            "created_at": order.created_at,
            "confirmed_at": order.confirmed_at,
        }

    def list_orders(self, skip: int = 0, limit: int = 10) -> dict:
        orders, total = self.repo.list_orders(skip, limit)

        order_list = []
        for order in orders:
            reservations = [
                {
                    "id": or_assoc.reservation.id,
                    "sku_id": or_assoc.reservation.sku_id,
                    "quantity": or_assoc.reservation.quantity,
                    "status": or_assoc.reservation.status,
                    "idempotency_key": or_assoc.reservation.idempotency_key,
                    "created_at": or_assoc.reservation.created_at,
                    "expires_at": or_assoc.reservation.expires_at,
                    "confirmed_at": or_assoc.reservation.confirmed_at,
                }
                for or_assoc in order.order_reservations
            ]

            order_list.append(
                {
                    "id": order.id,
                    "status": order.status,
                    "reservations": reservations,
                    "created_at": order.created_at,
                    "confirmed_at": order.confirmed_at,
                }
            )

        return {
            "orders": order_list,
            "total": total,
            "skip": skip,
            "limit": limit,
        }
