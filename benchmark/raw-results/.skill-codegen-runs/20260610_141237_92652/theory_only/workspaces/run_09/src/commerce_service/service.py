from datetime import datetime
from fastapi import HTTPException, status
from .repository import Repository
from .models import ReservationResponse, OrderResponse


class CommerceService:
    RESERVATION_TTL_SECONDS = 300

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        sku_id = self.repo.create_sku(sku, initial_stock)
        return {"id": sku_id, "sku": sku, "stock": initial_stock}

    def adjust_stock(self, sku: str, amount: int) -> dict:
        current_stock = self.repo.get_sku_stock(sku)
        if current_stock is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found",
            )
        new_stock = self.repo.adjust_stock(sku, amount)
        return {"sku": sku, "amount": amount, "new_stock": new_stock}

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> ReservationResponse:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return ReservationResponse(**existing)

        current_stock = self.repo.get_sku_stock(sku)
        if current_stock is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found",
            )

        if current_stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        self.repo.adjust_stock(sku, -quantity)
        reservation_id = self.repo.create_reservation(sku, quantity, idempotency_key)

        reservation = self.repo.get_reservation(reservation_id)
        return ReservationResponse(**reservation)

    def confirm_reservation(self, reservation_id: int) -> OrderResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reservation is not in PENDING status",
            )

        created_at = reservation["created_at"]
        elapsed = (datetime.utcnow() - created_at).total_seconds()
        if elapsed > self.RESERVATION_TTL_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order_id = self.repo.create_order(
            reservation_id, reservation["sku"], reservation["quantity"]
        )

        order = self.repo.get_order(order_id)
        return OrderResponse(**order)

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reservation is not in PENDING status",
            )

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])

        return {
            "id": reservation_id,
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": "CANCELLED",
        }

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.repo.get_orders(page, size)
        return {
            "orders": [OrderResponse(**order) for order in orders],
            "page": page,
            "size": size,
            "total": total,
        }
