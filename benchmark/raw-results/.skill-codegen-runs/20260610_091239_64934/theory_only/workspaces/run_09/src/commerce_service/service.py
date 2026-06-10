from datetime import datetime, timedelta

from .models import OrderResponse, ReservationResponse, ReservationStatus, StockResponse
from .repository import Repository


class ReservationExpiredError(Exception):
    pass


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class IdempotencyKeyExistsError(Exception):
    pass


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_code: str, name: str, description: str | None) -> dict:
        existing = self.repo.get_sku(sku_code)
        if existing:
            raise ValueError(f"SKU already exists: {sku_code}")

        sku = self.repo.create_sku(sku_code, name, description)
        self.repo.create_stock(sku_code, available=0)
        self.repo.commit()

        return {
            "sku_code": sku.sku_code,
            "name": sku.name,
            "description": sku.description,
            "created_at": sku.created_at,
        }

    def adjust_stock(self, sku_code: str, quantity: int) -> StockResponse:
        sku = self.repo.get_sku(sku_code)
        if not sku:
            raise SKUNotFoundError(f"SKU not found: {sku_code}")

        stock = self.repo.get_stock(sku_code)
        if stock.available + quantity < 0:
            raise InsufficientStockError(
                f"Cannot reduce stock below zero: available={stock.available}, delta={quantity}"
            )

        try:
            stock = self.repo.update_stock_available(sku_code, quantity)
        except ValueError as e:
            raise InsufficientStockError(str(e))

        self.repo.commit()

        return StockResponse(
            sku_code=stock.sku_code,
            available=stock.available,
            reserved=stock.reserved,
        )

    def create_reservation(
        self,
        sku_code: str,
        quantity: int,
        idempotency_key: str | None = None,
        reservation_duration_seconds: int = 3600,
    ) -> ReservationResponse:
        sku = self.repo.get_sku(sku_code)
        if not sku:
            raise SKUNotFoundError(f"SKU not found: {sku_code}")

        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                if existing.status == ReservationStatus.EXPIRED:
                    raise IdempotencyKeyExistsError(
                        f"Idempotency key already used (expired): {idempotency_key}"
                    )
                return self._format_reservation_response(existing)

        try:
            self.repo.reserve_stock(sku_code, quantity)
        except ValueError:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_code}: requested {quantity}"
            )

        expires_at = datetime.utcnow() + timedelta(seconds=reservation_duration_seconds)
        reservation = self.repo.create_reservation(
            sku_code, quantity, expires_at, idempotency_key
        )
        self.repo.commit()

        return self._format_reservation_response(reservation)

    def confirm_reservation(self, reservation_id: int) -> tuple[dict, dict]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation not found: {reservation_id}")

        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(
                f"Cannot confirm reservation with status: {reservation.status}"
            )

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(
                reservation_id, ReservationStatus.EXPIRED
            )
            self.repo.commit()
            raise ReservationExpiredError(
                f"Reservation has expired: {reservation_id}"
            )

        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED
        )
        order = self.repo.create_order(
            reservation.sku_code, reservation.quantity, reservation_id
        )
        self.repo.commit()

        return (
            self._format_reservation_response(reservation),
            {
                "id": order.id,
                "sku_code": order.sku_code,
                "quantity": order.quantity,
                "status": order.status,
                "created_at": order.created_at,
                "updated_at": order.updated_at,
            },
        )

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation not found: {reservation_id}")

        if reservation.status in (ReservationStatus.CONFIRMED, ReservationStatus.CANCELLED):
            raise ValueError(
                f"Cannot cancel reservation with status: {reservation.status}"
            )

        self.repo.release_reserved_stock(reservation.sku_code, reservation.quantity)
        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED
        )
        self.repo.commit()

        return self._format_reservation_response(reservation)

    def get_order(self, order_id: int) -> dict:
        order = self.repo.get_order(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        return {
            "id": order.id,
            "sku_code": order.sku_code,
            "quantity": order.quantity,
            "status": order.status,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }

    def list_orders(self, offset: int = 0, limit: int = 20) -> dict:
        orders, total = self.repo.list_orders(offset, limit)
        return {
            "orders": [
                {
                    "id": o.id,
                    "sku_code": o.sku_code,
                    "quantity": o.quantity,
                    "status": o.status,
                    "created_at": o.created_at,
                    "updated_at": o.updated_at,
                }
                for o in orders
            ],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    @staticmethod
    def _format_reservation_response(reservation) -> ReservationResponse:
        return ReservationResponse(
            id=reservation.id,
            sku_code=reservation.sku_code,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
        )
