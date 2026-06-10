"""Business logic service layer."""

from datetime import datetime, timezone

from fastapi import HTTPException, status

from .models import ReservationResponse, OrderResponse
from .repository import Repository


class Service:
    """Handles business logic for commerce operations."""

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock."""
        try:
            sku_id = self.repo.create_sku(sku, initial_stock)
            return {"id": sku_id, "sku": sku, "available_stock": initial_stock}
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"SKU '{sku}' already exists",
                )
            raise

    def adjust_stock(self, sku: str, amount: int) -> dict:
        """Adjust stock for a SKU."""
        stock = self.repo.get_sku_stock(sku)
        if stock is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU '{sku}' not found",
            )

        updated_stock = self.repo.adjust_stock(sku, amount)
        return {"sku": sku, "adjusted_by": amount, "new_stock": updated_stock}

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> ReservationResponse:
        """Create a reservation with idempotency."""
        # Check if already reserved with same idempotency key
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            # Return existing reservation without mutating stock
            created_at = datetime.fromisoformat(existing["created_at"])
            return ReservationResponse(
                id=existing["id"],
                sku=existing["sku"],
                quantity=existing["quantity"],
                status=existing["status"],
                idempotency_key=existing["idempotency_key"],
                created_at=created_at,
            )

        # Check stock availability
        stock = self.repo.get_sku_stock(sku)
        if stock is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU '{sku}' not found",
            )

        if stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        # Deduct stock and create reservation
        self.repo.adjust_stock(sku, -quantity)
        reservation_id = self.repo.create_reservation(sku, quantity, idempotency_key)

        reservation = self.repo.get_reservation(reservation_id)
        created_at = datetime.fromisoformat(reservation["created_at"])
        return ReservationResponse(
            id=reservation["id"],
            sku=reservation["sku"],
            quantity=reservation["quantity"],
            status=reservation["status"],
            idempotency_key=reservation["idempotency_key"],
            created_at=created_at,
        )

    def confirm_reservation(self, reservation_id: int) -> dict:
        """Confirm a reservation and create an order."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        # Check if status is PENDING
        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reservation is not in PENDING state (current: {reservation['status']})",
            )

        # Check expiration (300 seconds)
        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.now(timezone.utc)
        age = (now - created_at).total_seconds()

        if age > 300:
            # Mark as expired, restore stock, return error
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        # Update status and create order
        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order_id = self.repo.create_order(
            reservation_id, reservation["sku"], reservation["quantity"]
        )

        return {
            "reservation_id": reservation_id,
            "order_id": order_id,
            "status": "CONFIRMED",
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        """Cancel a reservation and restore stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        # Check if status is PENDING
        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reservation is not in PENDING state (current: {reservation['status']})",
            )

        # Restore stock and update status
        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
        self.repo.update_reservation_status(reservation_id, "CANCELLED")

        return {
            "reservation_id": reservation_id,
            "status": "CANCELLED",
            "stock_restored": reservation["quantity"],
        }

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        """Get paginated orders."""
        orders, total = self.repo.get_orders(page, size)
        return {
            "orders": orders,
            "page": page,
            "size": size,
            "total": total,
        }
