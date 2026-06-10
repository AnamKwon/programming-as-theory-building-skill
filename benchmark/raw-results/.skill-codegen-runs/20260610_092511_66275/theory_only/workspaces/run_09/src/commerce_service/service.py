from datetime import datetime
from commerce_service.repository import Repository
from commerce_service.models import (
    ReservationStatus,
    OrderStatus,
)


class ServiceError(Exception):
    pass


class InsufficientStockError(ServiceError):
    pass


class ReservationNotFoundError(ServiceError):
    pass


class ReservationExpiredError(ServiceError):
    pass


class InvalidReservationStateError(ServiceError):
    pass


class SkuNotFoundError(ServiceError):
    pass


class Service:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, name: str, total_stock: int) -> dict:
        sku = self.repo.create_sku(name, total_stock)
        return {
            "id": sku.id,
            "name": sku.name,
            "total_stock": sku.total_stock,
            "reserved_stock": sku.reserved_stock,
        }

    def adjust_stock(self, sku_id: int, adjustment: int) -> dict:
        sku = self.repo.adjust_stock(sku_id, adjustment)
        if not sku:
            raise SkuNotFoundError(f"SKU {sku_id} not found")
        return {
            "id": sku.id,
            "name": sku.name,
            "total_stock": sku.total_stock,
            "reserved_stock": sku.reserved_stock,
        }

    def create_reservation(self, sku_id: int, quantity: int, idempotency_key: str) -> dict:
        reservation = self.repo.create_reservation(sku_id, quantity, idempotency_key)
        if not reservation:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_id} (requested: {quantity})"
            )
        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": ReservationStatus(reservation.status),
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.confirm_reservation(reservation_id)
        if not reservation:
            db_res = self.repo.get_reservation(reservation_id)
            if not db_res:
                raise ReservationNotFoundError(f"Reservation {reservation_id} not found")
            if db_res.expires_at < datetime.utcnow():
                raise ReservationExpiredError(
                    f"Reservation {reservation_id} expired at {db_res.expires_at}"
                )
            raise InvalidReservationStateError(
                f"Reservation {reservation_id} is in {db_res.status} state"
            )

        order = self.repo.create_order(reservation_id)
        if not order:
            raise InvalidReservationStateError(
                f"Failed to create order for reservation {reservation_id}"
            )

        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": ReservationStatus(reservation.status),
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
            "order_id": order.id,
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.cancel_reservation(reservation_id)
        if not reservation:
            db_res = self.repo.get_reservation(reservation_id)
            if not db_res:
                raise ReservationNotFoundError(f"Reservation {reservation_id} not found")
            raise InvalidReservationStateError(
                f"Reservation {reservation_id} is in {db_res.status} state"
            )
        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": ReservationStatus(reservation.status),
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

    def get_orders(self, limit: int = 10, offset: int = 0) -> dict:
        orders, total = self.repo.get_orders(limit, offset)
        return {
            "orders": [
                {
                    "id": order.id,
                    "reservation_id": order.reservation_id,
                    "status": OrderStatus(order.status),
                    "created_at": order.created_at,
                }
                for order in orders
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
