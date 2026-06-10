from datetime import datetime, timedelta

from fastapi import HTTPException, status

from .repository import Database


class CommerceService:
    RESERVATION_TTL_MINUTES = 30

    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku: str, name: str, initial_stock: int = 0) -> dict:
        existing = self.db.get_sku_by_sku(sku)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"SKU '{sku}' already exists",
            )

        sku_id = self.db.create_sku(sku, name, initial_stock)
        return self.db.get_sku(sku_id)

    def adjust_stock(self, sku_id: int, adjustment: int) -> dict:
        sku = self.db.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )

        new_stock = sku["stock"] + adjustment
        if new_stock < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Adjustment would result in negative stock",
            )

        self.db.adjust_stock(sku_id, adjustment)
        return self.db.get_sku(sku_id)

    def create_reservation(
        self,
        order_id: str,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
    ) -> dict:
        existing_res = self.db.get_reservation_by_idempotency_key(idempotency_key)
        if existing_res:
            if (
                existing_res["order_id"] == order_id
                and existing_res["sku_id"] == sku_id
                and existing_res["quantity"] == quantity
            ):
                return existing_res

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key already used for different reservation",
            )

        sku = self.db.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )

        available_stock = sku["stock"] - sku["reserved"]
        if available_stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock. Available: {available_stock}, Requested: {quantity}",
            )

        self.db.create_or_get_order(order_id)

        expires_at = datetime.utcnow() + timedelta(
            minutes=self.RESERVATION_TTL_MINUTES
        )
        reservation_id = self.db.create_reservation(
            order_id, sku_id, quantity, idempotency_key, expires_at
        )

        self.db.reserve_stock(sku_id, quantity)

        return self.db.get_reservation(reservation_id)

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation["status"] != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot confirm reservation in '{reservation['status']}' status",
            )

        if datetime.utcnow() > reservation["expires_at"]:
            self.db.update_reservation_status(reservation_id, "cancelled")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation has expired",
            )

        self.db.update_reservation_status(reservation_id, "confirmed")
        return self.db.get_reservation(reservation_id)

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation["status"] == "cancelled":
            return reservation

        if reservation["status"] == "confirmed":
            self.db.release_stock(reservation["sku_id"], reservation["quantity"])

        self.db.update_reservation_status(reservation_id, "cancelled")
        return self.db.get_reservation(reservation_id)

    def get_orders(self, limit: int = 50, offset: int = 0) -> dict:
        if limit < 1 or limit > 100:
            limit = 50
        if offset < 0:
            offset = 0

        orders, total = self.db.list_orders(limit, offset)
        return {
            "items": orders,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
