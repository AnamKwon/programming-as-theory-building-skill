from datetime import datetime, timedelta

from .models import ReservationStatus, OrderStatus
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class CommerceService:
    RESERVATION_TTL = 300  # 5 minutes

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, code: str) -> dict:
        sku = self.repo.create_sku(code)
        self.repo.create_stock(sku.id, 0)
        self.repo.commit()
        return {"id": sku.id, "code": sku.code}

    def adjust_stock(self, sku_code: str, delta: int) -> dict:
        sku = self.repo.get_sku_by_code(sku_code)
        if not sku:
            raise SKUNotFoundError(f"SKU not found: {sku_code}")

        stock = self.repo.update_stock(sku.id, delta)
        self.repo.commit()
        return {"sku_code": sku_code, "quantity": stock.quantity}

    def create_reservation(
        self, sku_code: str, quantity: int, idempotency_key: str
    ) -> dict:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == ReservationStatus.EXPIRED:
                raise ReservationExpiredError("Reservation has expired")
            return self._format_reservation(existing)

        sku = self.repo.get_sku_by_code(sku_code)
        if not sku:
            raise SKUNotFoundError(f"SKU not found: {sku_code}")

        stock = self.repo.get_stock_by_sku_id(sku.id)
        available = (stock.quantity if stock else 0) - self.repo.get_reserved_quantity(
            sku.id
        )

        if available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock. Available: {available}, requested: {quantity}"
            )

        expires_at = datetime.utcnow() + timedelta(seconds=self.RESERVATION_TTL)
        reservation = self.repo.create_reservation(
            idempotency_key, sku.id, quantity, expires_at
        )
        self.repo.commit()
        return self._format_reservation(reservation)

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation not found: {reservation_id}")

        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(f"Cannot confirm reservation in {reservation.status} status")

        if reservation.expires_at < datetime.utcnow():
            self.repo.update_reservation_status(
                reservation_id, ReservationStatus.EXPIRED
            )
            self.repo.commit()
            raise ReservationExpiredError("Reservation has expired")

        order = self.repo.create_order(reservation.sku_id, reservation.quantity)
        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED, order.id
        )
        self.repo.commit()

        sku = self.repo.get_sku_by_id(reservation.sku_id)
        return {
            "order_id": order.id,
            "sku_code": sku.code if sku else "unknown",
            "quantity": order.quantity,
            "status": order.status.value,
            "created_at": order.created_at.isoformat(),
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation not found: {reservation_id}")

        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(
                f"Cannot cancel reservation in {reservation.status} status"
            )

        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED
        )
        self.repo.commit()
        return {"id": reservation_id, "status": ReservationStatus.CANCELLED.value}

    def get_order(self, order_id: int) -> dict:
        order = self.repo.get_order_by_id(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        sku = self.repo.get_sku_by_id(order.sku_id)
        return {
            "id": order.id,
            "sku_code": sku.code if sku else "unknown",
            "quantity": order.quantity,
            "status": order.status.value,
            "created_at": order.created_at.isoformat(),
        }

    def list_orders(self, limit: int = 10, offset: int = 0) -> dict:
        orders, total = self.repo.list_orders(limit, offset)
        return {
            "orders": [
                {
                    "id": o.id,
                    "sku_code": (self.repo.get_sku_by_id(o.sku_id).code if self.repo.get_sku_by_id(o.sku_id) else "unknown"),
                    "quantity": o.quantity,
                    "status": o.status.value,
                    "created_at": o.created_at.isoformat(),
                }
                for o in orders
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def _format_reservation(self, reservation) -> dict:
        sku = self.repo.get_sku_by_id(reservation.sku_id)
        return {
            "id": reservation.id,
            "sku_code": sku.code if sku else "unknown",
            "quantity": reservation.quantity,
            "status": reservation.status.value,
            "created_at": reservation.created_at.isoformat(),
            "expires_at": reservation.expires_at.isoformat(),
        }
