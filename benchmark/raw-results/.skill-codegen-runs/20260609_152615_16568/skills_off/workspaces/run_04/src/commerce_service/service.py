from datetime import datetime, timedelta
from fastapi import HTTPException
from .repository import Repository
from .models import ReservationStatus, OrderStatus


class CommerceService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, name: str) -> dict:
        try:
            sku_id = self.repo.create_sku(name)
            return self.repo.get_sku(sku_id)
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                raise HTTPException(
                    status_code=409, detail=f"SKU with name '{name}' already exists"
                )
            raise

    def adjust_stock(self, sku_id: int, delta: int) -> dict:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise HTTPException(status_code=404, detail="SKU not found")

        stock = self.repo.adjust_stock(sku_id, delta)
        if stock["quantity"] < 0:
            raise HTTPException(status_code=400, detail="Stock cannot be negative")
        return stock

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str, ttl_seconds: int
    ) -> dict:
        # Check for idempotency: if this key exists, return it
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing["status"] == ReservationStatus.CANCELLED:
                raise HTTPException(
                    status_code=409,
                    detail="Cannot reuse idempotency key for cancelled reservation",
                )
            return existing

        # Validate SKU exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise HTTPException(status_code=404, detail="SKU not found")

        # Check stock availability
        stock = self.repo.get_stock(sku_id)
        available = stock["quantity"] if stock else 0
        if available < quantity:
            raise HTTPException(
                status_code=409,
                detail=f"Insufficient stock: requested {quantity}, available {available}",
            )

        # Create reservation
        expires_at = (datetime.utcnow() + timedelta(seconds=ttl_seconds)).isoformat()
        reservation_id = self.repo.create_reservation(
            sku_id, quantity, idempotency_key, expires_at
        )
        return self.repo.get_reservation(reservation_id)

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        # Check expiration
        if datetime.fromisoformat(reservation["expires_at"]) < datetime.utcnow():
            raise HTTPException(status_code=410, detail="Reservation has expired")

        # Check status
        if reservation["status"] != ReservationStatus.RESERVED:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot confirm reservation in {reservation['status']} status",
            )

        # Confirm and create order
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)
        order_id = self.repo.create_order(
            reservation_id, reservation["sku_id"], reservation["quantity"]
        )

        # Deduct from stock
        self.repo.adjust_stock(reservation["sku_id"], -reservation["quantity"])

        return self.repo.get_reservation(reservation_id)

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation["status"] != ReservationStatus.RESERVED:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot cancel reservation in {reservation['status']} status",
            )

        return self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED
        )

    def get_order(self, order_id: int) -> dict:
        order = self.repo.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        return order

    def list_orders(self, limit: int = 20, cursor: int = 0) -> tuple[list[dict], int | None]:
        return self.repo.list_orders(limit, cursor)
