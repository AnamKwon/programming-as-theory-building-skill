from datetime import datetime
from fastapi import HTTPException, status
from .repository import Database


class CommerceService:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        try:
            return self.db.create_sku(sku, initial_stock)
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="SKU already exists"
                )
            raise

    def adjust_stock(self, sku: str, amount: int) -> dict:
        sku_record = self.db.get_sku(sku)
        if not sku_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found"
            )
        return self.db.update_sku_stock(sku, amount)

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str
    ) -> tuple[dict, int]:
        existing = self.db.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing, 200

        sku_record = self.db.get_sku(sku)
        if not sku_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found"
            )

        if sku_record["available_stock"] < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock"
            )

        self.db.update_sku_stock(sku, -quantity)
        created_at = datetime.utcnow()
        reservation = self.db.create_reservation(sku, quantity, idempotency_key, created_at)
        return reservation, 201

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found"
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not pending"
            )

        now = datetime.utcnow()
        elapsed = (now - reservation["created_at"]).total_seconds()
        if elapsed > 300:
            self.db.update_reservation_status(reservation_id, "EXPIRED")
            self.db.update_sku_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired"
            )

        self.db.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.db.create_order(reservation_id, now)
        return order

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found"
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not pending"
            )

        self.db.update_reservation_status(reservation_id, "CANCELLED")
        self.db.update_sku_stock(reservation["sku"], reservation["quantity"])
        return {"status": "cancelled"}

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.db.get_orders(page, size)
        return {
            "page": page,
            "size": size,
            "total": total,
            "items": orders
        }
