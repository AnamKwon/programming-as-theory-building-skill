from datetime import datetime, timezone
from typing import Dict, Any
from fastapi import HTTPException, status
from .repository import Database, SKURepository, ReservationRepository, OrderRepository
from .models import ReservationResponse, OrderResponse, StockResponse


class CommerceService:
    RESERVATION_EXPIRATION_SECONDS = 300

    def __init__(self, db: Database):
        self.db = db
        self.sku_repo = SKURepository(db)
        self.reservation_repo = ReservationRepository(db)
        self.order_repo = OrderRepository(db)

    def create_sku(self, sku: str, initial_stock: int):
        try:
            return self.sku_repo.create_sku(sku, initial_stock)
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"SKU {sku} already exists",
                )
            raise

    def adjust_stock(self, sku: str, amount: int) -> StockResponse:
        try:
            result = self.sku_repo.adjust_stock(sku, amount)
            return StockResponse(**result)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found",
            )

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> ReservationResponse:
        # Check for existing idempotent reservation
        existing = self.reservation_repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return ReservationResponse(**existing)

        # Get SKU and check stock
        sku_data = self.sku_repo.get_sku_by_name(sku)
        if not sku_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found",
            )

        if sku_data["available_stock"] < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        # Deduct stock and create reservation
        self.reservation_repo.deduct_stock(sku_data["id"], quantity)
        result = self.reservation_repo.create_reservation(
            sku_data["id"], sku, quantity, idempotency_key
        )
        return ReservationResponse(**result)

    def confirm_reservation(self, reservation_id: int) -> Dict:
        reservation = self.reservation_repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reservation is not PENDING",
            )

        # Check expiration (created more than 300 seconds ago)
        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.now(timezone.utc)
        elapsed = (now - created_at).total_seconds()

        if elapsed > self.RESERVATION_EXPIRATION_SECONDS:
            # Mark as expired and restore stock
            self.reservation_repo.mark_expired(reservation_id)
            self.reservation_repo.restore_stock(reservation["sku_id"], reservation["quantity"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        # Confirm reservation and create order
        self.reservation_repo.confirm_reservation(reservation_id)
        order = self.order_repo.create_order(reservation_id)
        return OrderResponse(**order)

    def cancel_reservation(self, reservation_id: int) -> Dict:
        reservation = self.reservation_repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reservation is not PENDING",
            )

        # Cancel and restore stock
        self.reservation_repo.cancel_reservation(reservation_id)
        self.reservation_repo.restore_stock(reservation["sku_id"], reservation["quantity"])

        return {
            "id": reservation["id"],
            "status": "CANCELLED",
            "message": "Reservation cancelled and stock restored",
        }

    def get_orders_paginated(self, page: int = 1, size: int = 10):
        if page < 1 or size < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="page and size must be >= 1",
            )

        orders, total = self.order_repo.get_orders_paginated(page, size)
        return {
            "orders": [OrderResponse(**order) for order in orders],
            "page": page,
            "size": size,
            "total": total,
        }
