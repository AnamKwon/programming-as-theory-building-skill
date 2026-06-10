from datetime import datetime, timezone
from fastapi import HTTPException, status
from .repository import Database


class CommerceService:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.db.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        result = self.db.adjust_stock(sku, amount)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )
        return result

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        existing = self.db.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        stock = self.db.get_sku_stock(sku)
        if stock is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )

        if stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        self.db.adjust_stock(sku, -quantity)
        reservation = self.db.create_reservation(sku, quantity, idempotency_key)
        return reservation

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not pending",
            )

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.now(timezone.utc)
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > 300:
            self.db.update_reservation_status(reservation_id, "EXPIRED")
            self.db.adjust_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        now_iso = now.isoformat()
        self.db.update_reservation_status(reservation_id, "CONFIRMED", now_iso)

        order = self.db.create_order(
            reservation_id, reservation["sku"], reservation["quantity"]
        )

        return {
            "id": reservation_id,
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": "CONFIRMED",
            "order_id": order["id"],
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not pending",
            )

        self.db.update_reservation_status(reservation_id, "CANCELLED")
        self.db.adjust_stock(reservation["sku"], reservation["quantity"])

        return {
            "id": reservation_id,
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": "CANCELLED",
            "restored_stock": reservation["quantity"],
        }

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.db.get_orders(page, size)
        return {
            "items": orders,
            "page": page,
            "size": size,
            "total": total,
        }
