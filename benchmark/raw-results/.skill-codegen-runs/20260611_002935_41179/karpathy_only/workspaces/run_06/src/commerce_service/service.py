from datetime import datetime
from fastapi import HTTPException, status
from .repository import Repository
from .models import ReservationResponse, ConfirmReservationResponse


class Service:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        success = self.repo.create_sku(sku, initial_stock)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"SKU {sku} already exists",
            )
        return {"sku": sku, "stock": initial_stock}

    def adjust_stock(self, sku: str, amount: int) -> dict:
        new_stock = self.repo.adjust_stock(sku, amount)
        if new_stock is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found",
            )
        return {"sku": sku, "stock": new_stock}

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> ReservationResponse:
        # Check idempotency
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return ReservationResponse(
                id=existing["id"],
                sku=existing["sku"],
                quantity=existing["quantity"],
                status=existing["status"],
                timestamp=datetime.fromisoformat(existing["timestamp"]),
                idempotency_key=existing["idempotency_key"],
            )

        # Check stock
        stock = self.repo.get_sku_stock(sku)
        if stock is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found",
            )
        if stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        # Create reservation and adjust stock
        reservation_id = self.repo.create_reservation(
            sku, quantity, idempotency_key
        )
        self.repo.adjust_stock(sku, -quantity)

        return ReservationResponse(
            id=reservation_id,
            sku=sku,
            quantity=quantity,
            status="PENDING",
            timestamp=datetime.utcnow(),
            idempotency_key=idempotency_key,
        )

    def confirm_reservation(self, reservation_id: int) -> ConfirmReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not pending",
            )

        # Check expiration (300 seconds)
        created_at = datetime.fromisoformat(reservation["timestamp"])
        age_seconds = (datetime.utcnow() - created_at).total_seconds()
        if age_seconds > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        # Create order and update reservation status
        order_id = self.repo.create_order(
            reservation_id, reservation["sku"], reservation["quantity"]
        )
        self.repo.update_reservation_status(reservation_id, "CONFIRMED")

        return ConfirmReservationResponse(
            reservation_id=reservation_id,
            order_id=order_id,
            sku=reservation["sku"],
            quantity=reservation["quantity"],
            timestamp=datetime.utcnow(),
        )

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
                detail="Reservation is not pending",
            )

        # Restore stock and update status
        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
        self.repo.update_reservation_status(reservation_id, "CANCELLED")

        return {
            "id": reservation_id,
            "status": "CANCELLED",
            "stock_restored": reservation["quantity"],
        }

    def list_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.repo.list_orders(page, size)
        return {
            "items": [
                {
                    "id": order["id"],
                    "reservation_id": order["reservation_id"],
                    "sku": order["sku"],
                    "quantity": order["quantity"],
                    "timestamp": order["timestamp"],
                }
                for order in orders
            ],
            "page": page,
            "size": size,
            "total": total,
        }
