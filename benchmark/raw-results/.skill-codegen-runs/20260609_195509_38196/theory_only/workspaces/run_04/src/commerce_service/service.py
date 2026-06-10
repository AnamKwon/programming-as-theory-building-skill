from datetime import datetime, UTC
from fastapi import HTTPException, status
from commerce_service.repository import Database
from commerce_service.models import (
    ReservationStatus,
    OrderStatus,
)


class CommerceService:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, name: str, quantity: int) -> dict:
        sku_id = self.db.create_sku(name, quantity)
        return {"id": sku_id, "name": name, "quantity_available": quantity}

    def adjust_stock(self, sku_id: int, quantity_delta: int) -> dict:
        sku = self.db.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )
        if not self.db.adjust_stock(sku_id, quantity_delta):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock for adjustment",
            )
        updated_sku = self.db.get_sku(sku_id)
        return updated_sku

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str
    ) -> dict:
        sku = self.db.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )

        existing = self.db.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing["status"] in (
                ReservationStatus.CANCELLED,
                ReservationStatus.CONFIRMED,
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Idempotency key already used in {existing['status']} reservation",
                )
            return self._format_reservation(existing)

        available = self.db.get_available_stock(sku_id)
        if available < quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Insufficient available stock",
            )

        reservation_id = self.db.create_reservation(sku_id, quantity, idempotency_key)
        if not reservation_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key already used",
            )

        reservation = self.db.get_reservation(reservation_id)
        return self._format_reservation(reservation)

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation["status"] != ReservationStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot confirm {reservation['status']} reservation",
            )

        expires_at = datetime.fromisoformat(reservation["expires_at"])
        if datetime.now(UTC) > expires_at:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reservation has expired",
            )

        self.db.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)
        self.db.create_order(reservation["sku_id"], reservation["quantity"])

        updated = self.db.get_reservation(reservation_id)
        return self._format_reservation(updated)

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation["status"] != ReservationStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot cancel {reservation['status']} reservation",
            )

        self.db.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
        updated = self.db.get_reservation(reservation_id)
        return self._format_reservation(updated)

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        if page < 1 or size < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="page and size must be >= 1",
            )
        skip = (page - 1) * size
        orders, total = self.db.get_orders(skip, size)
        return {
            "items": [self._format_order(o) for o in orders],
            "total": total,
            "page": page,
            "size": size,
        }

    def _format_reservation(self, row: dict) -> dict:
        return {
            "id": row["id"],
            "sku_id": row["sku_id"],
            "quantity": row["quantity"],
            "status": row["status"],
            "expires_at": row["expires_at"],
            "created_at": row["created_at"],
        }

    def _format_order(self, row: dict) -> dict:
        return {
            "id": row["id"],
            "sku_id": row["sku_id"],
            "quantity": row["quantity"],
            "status": row["status"],
            "created_at": row["created_at"],
        }
