from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from commerce_service.repository import Repository


class CommerceService:
    def __init__(self, db: Session):
        self.repo = Repository(db)

    def create_sku(self, sku_name: str, initial_stock: int):
        try:
            sku = self.repo.create_sku(sku_name, initial_stock)
            return {
                "id": sku.id,
                "sku_name": sku.sku_name,
                "available_stock": sku.available_stock,
                "reserved_stock": sku.reserved_stock,
            }
        except IntegrityError:
            raise ValueError(f"SKU '{sku_name}' already exists")

    def adjust_stock(self, sku_id: int, quantity_delta: int):
        sku = self.repo.adjust_stock(sku_id, quantity_delta)
        return {
            "id": sku.id,
            "sku_name": sku.sku_name,
            "available_stock": sku.available_stock,
            "reserved_stock": sku.reserved_stock,
        }

    def create_reservation(self, sku_id: int, quantity: int, idempotency_key: str):
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == "cancelled":
                raise ValueError("Reservation with this idempotency key was cancelled")
            return self._format_reservation(existing)

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        if sku.available_stock < quantity:
            raise ValueError(
                f"Insufficient stock. Required: {quantity}, Available: {sku.available_stock}"
            )

        try:
            reservation = self.repo.create_reservation(sku_id, quantity, idempotency_key)
            sku.available_stock -= quantity
            sku.reserved_stock += quantity
            return self._format_reservation(reservation)
        except IntegrityError:
            raise ValueError("Idempotency key conflict; reservation may already exist")

    def confirm_reservation(self, reservation_id: int):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "pending":
            raise ValueError(f"Reservation is not pending; status: {reservation.status}")

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, "expired")
            sku = self.repo.get_sku(reservation.sku_id)
            if sku:
                sku.available_stock += reservation.quantity
                sku.reserved_stock -= reservation.quantity
            raise ValueError("Reservation has expired")

        self.repo.update_reservation_status(reservation_id, "confirmed")
        order = self.repo.create_order(reservation_id, status="confirmed")

        sku = self.repo.get_sku(reservation.sku_id)
        if sku:
            sku.reserved_stock -= reservation.quantity

        return {
            "order_id": order.id,
            "reservation_id": reservation_id,
            "status": "confirmed",
            "created_at": order.created_at,
        }

    def cancel_reservation(self, reservation_id: int):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status == "confirmed":
            raise ValueError("Cannot cancel a confirmed reservation")

        if reservation.status == "cancelled":
            raise ValueError("Reservation is already cancelled")

        self.repo.update_reservation_status(reservation_id, "cancelled")

        sku = self.repo.get_sku(reservation.sku_id)
        if sku:
            sku.available_stock += reservation.quantity
            sku.reserved_stock -= reservation.quantity

        return {
            "reservation_id": reservation_id,
            "status": "cancelled",
        }

    def get_orders(self, limit: int = 10, offset: int = 0):
        orders, total = self.repo.get_orders(limit, offset)
        return {
            "orders": [self._format_order(o) for o in orders],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def _format_reservation(self, reservation):
        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
            "idempotency_key": reservation.idempotency_key,
        }

    def _format_order(self, order):
        return {
            "id": order.id,
            "reservation_id": order.reservation_id,
            "status": order.status,
            "created_at": order.created_at,
        }
