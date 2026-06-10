from datetime import datetime
from fastapi import HTTPException, status

from .models import ReservationStatus, OrderStatus
from .repository import Database


class CommerceService:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, code: str, name: str, initial_stock: int) -> dict:
        try:
            sku_id = self.db.create_sku(code, name, initial_stock)
            return {
                "id": sku_id,
                "code": code,
                "name": name,
                "current_stock": initial_stock,
                "reserved_stock": 0,
            }
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"SKU with code '{code}' already exists",
            )

    def adjust_stock(self, sku_id: int, quantity: int) -> dict:
        sku = self.db.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )
        self.db.adjust_stock(sku_id, quantity)
        sku = self.db.get_sku(sku_id)
        return {
            "id": sku["id"],
            "code": sku["code"],
            "name": sku["name"],
            "current_stock": sku["current_stock"],
            "reserved_stock": sku["reserved_stock"],
        }

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str
    ) -> dict:
        existing = self.db.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing["status"] == ReservationStatus.EXPIRED.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Reservation has expired",
                )
            return self._format_reservation(existing)

        sku = self.db.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )

        available = sku["current_stock"] - sku["reserved_stock"]
        if available < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock. Available: {available}, Requested: {quantity}",
            )

        reservation_id = self.db.create_reservation(sku_id, quantity, idempotency_key)
        self.db.update_reserved_stock(sku_id, quantity)

        reservation = self.db.get_reservation(reservation_id)
        return self._format_reservation(reservation)

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation["status"] == ReservationStatus.EXPIRED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot confirm an expired reservation",
            )

        if reservation["status"] != ReservationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reservation is {reservation['status']}, cannot confirm",
            )

        now = datetime.utcnow()
        expires_at = datetime.fromisoformat(reservation["expires_at"])
        if now > expires_at:
            self.db.expire_reservation(reservation_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation has expired",
            )

        self.db.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED
        )
        order_id = self.db.create_order(
            reservation["sku_id"], reservation["quantity"], reservation_id
        )
        self.db.update_reserved_stock(reservation["sku_id"], -reservation["quantity"])
        self.db.adjust_stock(reservation["sku_id"], -reservation["quantity"])

        reservation = self.db.get_reservation(reservation_id)
        return self._format_reservation(reservation)

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation["status"] != ReservationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel a {reservation['status']} reservation",
            )

        self.db.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED
        )
        self.db.update_reserved_stock(reservation["sku_id"], -reservation["quantity"])

        reservation = self.db.get_reservation(reservation_id)
        return self._format_reservation(reservation)

    def get_order(self, order_id: int) -> dict:
        order = self.db.get_order(order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found",
            )
        return self._format_order(order)

    def list_orders(self, offset: int = 0, limit: int = 20) -> dict:
        if offset < 0 or limit <= 0 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid pagination parameters",
            )
        items, total = self.db.list_orders(offset, limit)
        return {
            "items": [self._format_order(item) for item in items],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    def _format_reservation(self, row: dict) -> dict:
        return {
            "id": row["id"],
            "sku_id": row["sku_id"],
            "quantity": row["quantity"],
            "status": row["status"],
            "idempotency_key": row["idempotency_key"],
            "created_at": datetime.fromisoformat(row["created_at"]),
            "expires_at": datetime.fromisoformat(row["expires_at"]),
        }

    def _format_order(self, row: dict) -> dict:
        return {
            "id": row["id"],
            "sku_id": row["sku_id"],
            "quantity": row["quantity"],
            "status": row["status"],
            "reservation_id": row["reservation_id"],
            "created_at": datetime.fromisoformat(row["created_at"]),
        }


import sqlite3
