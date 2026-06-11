from datetime import datetime, timezone
from typing import Optional, Tuple, List
from fastapi import HTTPException, status
from .repository import Repository
from .models import ReservationResponse, OrderResponse


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        self.repo.create_sku(sku, initial_stock)
        return {"sku": sku, "initial_stock": initial_stock}

    def adjust_stock(self, sku: str, amount: int) -> dict:
        sku_data = self.repo.get_sku(sku)
        if not sku_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found",
            )
        result = self.repo.adjust_stock(sku, amount)
        return {"sku": sku, "available_stock": result["available_stock"]}

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Tuple[ReservationResponse, int]:
        existing = self.repo.check_idempotency_key(idempotency_key)
        if existing:
            return (
                ReservationResponse(
                    id=existing["id"],
                    sku=existing["sku"],
                    quantity=existing["quantity"],
                    status=existing["status"],
                    created_at=existing["created_at"],
                    idempotency_key=existing["idempotency_key"],
                ),
                200,
            )

        available_stock = self.repo.get_available_stock(sku)
        if available_stock is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found",
            )
        if available_stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        created_at = datetime.now(timezone.utc).isoformat()
        reservation_id = self.repo.create_reservation(
            sku, quantity, idempotency_key, created_at
        )
        self.repo.deduct_stock(sku, quantity)

        return (
            ReservationResponse(
                id=reservation_id,
                sku=sku,
                quantity=quantity,
                status="PENDING",
                created_at=created_at,
                idempotency_key=idempotency_key,
            ),
            201,
        )

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reservation is not in PENDING status",
            )

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        elapsed = (now - created_at).total_seconds()
        if elapsed > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order_created_at = datetime.now(timezone.utc).isoformat()
        order_id = self.repo.create_order(reservation_id, order_created_at)

        return {
            "id": reservation_id,
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": "CONFIRMED",
            "created_at": reservation["created_at"],
            "idempotency_key": reservation["idempotency_key"],
            "order_id": order_id,
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
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
            "created_at": reservation["created_at"],
            "idempotency_key": reservation["idempotency_key"],
        }

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.repo.get_orders(page, size)
        return {
            "orders": [
                OrderResponse(
                    id=order["id"],
                    reservation_id=order["reservation_id"],
                    created_at=order["created_at"],
                )
                for order in orders
            ],
            "page": page,
            "size": size,
            "total": total,
        }
