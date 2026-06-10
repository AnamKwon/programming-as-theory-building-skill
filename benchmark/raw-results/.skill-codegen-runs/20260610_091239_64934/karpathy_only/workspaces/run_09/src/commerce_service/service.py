from datetime import datetime
from sqlite3 import IntegrityError

from fastapi import HTTPException, status

from .models import OrderStatus, ReservationStatus
from .repository import Database


class CommerceService:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku_id: str, name: str, initial_stock: int) -> dict:
        try:
            return self.db.create_sku(sku_id, name, initial_stock)
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"SKU {sku_id} already exists",
            )

    def get_sku(self, sku_id: str) -> dict:
        sku = self.db.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )
        return sku

    def adjust_stock(self, sku_id: str, quantity_delta: int) -> dict:
        sku = self.db.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )

        new_stock = sku["stock_quantity"] + quantity_delta
        if new_stock < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stock adjustment would result in negative inventory",
            )

        return self.db.adjust_stock(sku_id, quantity_delta)

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str
    ) -> dict:
        # Check for idempotent retry
        existing = self.db.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        # Verify SKU exists and has sufficient stock
        sku = self.db.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )

        if sku["stock_quantity"] < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock: {sku['stock_quantity']} available, {quantity} requested",
            )

        # Create the reservation
        try:
            return self.db.create_reservation(sku_id, quantity, idempotency_key)
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key already used",
            )

    def confirm_reservation(self, reservation_id: str) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        # Check expiration
        if self._is_expired(reservation):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation has expired",
            )

        # Check status
        if reservation["status"] != ReservationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot confirm reservation with status {reservation['status']}",
            )

        # Create order and confirm reservation atomically
        order = self.db.create_order(reservation["sku_id"], reservation["quantity"])
        self.db.confirm_reservation(reservation_id)

        # Reduce stock
        self.db.adjust_stock(reservation["sku_id"], -reservation["quantity"])

        return reservation

    def cancel_reservation(self, reservation_id: str) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation["status"] != ReservationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel reservation with status {reservation['status']}",
            )

        return self.db.cancel_reservation(reservation_id)

    def get_order(self, order_id: str) -> dict:
        order = self.db.get_order(order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found",
            )
        return order

    def list_orders(self, limit: int, offset: int) -> tuple[list[dict], int]:
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Limit must be between 1 and 100",
            )
        if offset < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Offset must be non-negative",
            )
        return self.db.list_orders(limit, offset)

    def _is_expired(self, reservation: dict) -> bool:
        return datetime.utcnow() > reservation["expires_at"]
