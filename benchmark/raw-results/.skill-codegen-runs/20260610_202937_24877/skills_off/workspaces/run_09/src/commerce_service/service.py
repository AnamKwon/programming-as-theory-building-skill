from datetime import datetime
from sqlalchemy.orm import Session

from .models import ReservationStatus, ReservationResponse, OrderResponse
from .repository import Repository


class CommerceService:
    def __init__(self, db: Session):
        self.repo = Repository(session=db)

    def create_sku(self, sku: str, initial_stock: int):
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int):
        sku_obj = self.repo.get_sku_by_sku_code(sku)
        if not sku_obj:
            return None
        updated = self.repo.update_sku_stock(sku_obj.id, amount)
        return updated

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> tuple[dict, int]:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return {
                "id": existing.id,
                "sku": existing.sku.sku,
                "quantity": existing.quantity,
                "status": existing.status.value,
                "created_at": existing.created_at.isoformat(),
                "idempotency_key": existing.idempotency_key,
            }, 201

        sku_obj = self.repo.get_sku_by_sku_code(sku)
        if not sku_obj:
            return {"detail": "SKU not found"}, 404

        if sku_obj.available_stock < quantity:
            return {"detail": "Insufficient stock"}, 400

        self.repo.update_sku_stock(sku_obj.id, -quantity)

        reservation = self.repo.create_reservation(sku_obj.id, quantity, idempotency_key)

        return {
            "id": reservation.id,
            "sku": sku,
            "quantity": quantity,
            "status": reservation.status.value,
            "created_at": reservation.created_at.isoformat(),
            "idempotency_key": idempotency_key,
        }, 201

    def confirm_reservation(self, reservation_id: int) -> tuple[dict, int]:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            return {"detail": "Reservation not found"}, 404

        if reservation.status != ReservationStatus.PENDING:
            return {"detail": f"Cannot confirm reservation with status {reservation.status.value}"}, 400

        created_at = reservation.created_at
        now = datetime.utcnow()
        elapsed = (now - created_at).total_seconds()

        if elapsed > 300:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            self.repo.update_sku_stock(reservation.sku_id, reservation.quantity)
            return {"detail": "Reservation expired"}, 400

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)
        order = self.repo.create_order(reservation_id)

        return {
            "id": order.id,
            "reservation_id": order.reservation_id,
            "created_at": order.created_at.isoformat(),
        }, 200

    def cancel_reservation(self, reservation_id: int) -> tuple[dict, int]:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            return {"detail": "Reservation not found"}, 404

        if reservation.status != ReservationStatus.PENDING:
            return {"detail": f"Cannot cancel reservation with status {reservation.status.value}"}, 400

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
        self.repo.update_sku_stock(reservation.sku_id, reservation.quantity)

        return {
            "id": reservation.id,
            "sku": reservation.sku.sku,
            "quantity": reservation.quantity,
            "status": ReservationStatus.CANCELLED.value,
            "created_at": reservation.created_at.isoformat(),
            "idempotency_key": reservation.idempotency_key,
        }, 200

    def get_orders(self, page: int = 1, size: int = 10):
        orders, total = self.repo.get_orders_paginated(page, size)
        pages = (total + size - 1) // size

        return {
            "items": [
                {
                    "id": order.id,
                    "reservation_id": order.reservation_id,
                    "created_at": order.created_at.isoformat(),
                }
                for order in orders
            ],
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        }, 200
