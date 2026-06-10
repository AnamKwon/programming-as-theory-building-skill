from datetime import datetime
from fastapi import HTTPException, status
from .repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock."""
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        """Adjust stock for a SKU."""
        result = self.repo.adjust_stock(sku, amount)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found",
            )
        return result

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        """Create a reservation with idempotency."""
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return {
                "id": existing["id"],
                "sku": existing["sku"],
                "quantity": existing["quantity"],
                "status": existing["status"],
                "created_at": existing["created_at"],
                "confirmed_at": existing["confirmed_at"],
            }

        sku_data = self.repo.get_sku_by_code(sku)
        if sku_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found",
            )

        if sku_data["available_stock"] < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        self.repo.adjust_stock(sku, -quantity)
        reservation = self.repo.create_reservation(
            sku_data["id"], sku, quantity, idempotency_key
        )
        return reservation

    def confirm_reservation(self, reservation_id: int) -> dict:
        """Confirm a pending reservation and create an order."""
        reservation = self.repo.get_reservation(reservation_id)
        if reservation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not in PENDING state",
            )

        now = datetime.utcnow()
        created_at = reservation["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elapsed = (now - created_at).total_seconds()

        if elapsed > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        self.repo.update_reservation_status(reservation_id, "CONFIRMED", now)
        self.repo.create_order(reservation_id)

        return {
            "id": reservation_id,
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": "CONFIRMED",
            "created_at": reservation["created_at"],
            "confirmed_at": now,
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        """Cancel a reservation and restore stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if reservation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not in PENDING state",
            )

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])

        return {
            "id": reservation_id,
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": "CANCELLED",
            "created_at": reservation["created_at"],
            "confirmed_at": reservation["confirmed_at"],
        }

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        """Get paginated orders."""
        return self.repo.get_orders(page, size)
