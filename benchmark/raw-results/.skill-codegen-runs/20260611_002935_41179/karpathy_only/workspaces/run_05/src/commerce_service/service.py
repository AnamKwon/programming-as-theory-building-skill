"""Business logic service layer."""

from datetime import datetime, timezone

from .models import (
    ConfirmReservationResponse,
    OrderResponse,
    PaginatedOrdersResponse,
    ReservationResponse,
    StockAdjustResponse,
)
from .repository import Repository


class CommerceService:
    """Service layer for commerce operations."""

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU."""
        self.repo.create_sku(sku, initial_stock)
        sku_data = self.repo.get_sku_by_name(sku)
        return {"id": sku_data["id"], "sku": sku_data["sku"], "available_stock": sku_data["available_stock"]}

    def adjust_stock(self, sku: str, amount: int) -> StockAdjustResponse:
        """Adjust stock for a SKU."""
        result = self.repo.adjust_stock(sku, amount)
        if result is None:
            raise ValueError(f"SKU not found: {sku}")
        return StockAdjustResponse(**result)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> ReservationResponse:
        """Create a reservation with idempotency check."""
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return ReservationResponse(**existing)

        sku_data = self.repo.get_sku_by_name(sku)
        if sku_data is None:
            raise ValueError(f"SKU not found: {sku}")

        if sku_data["available_stock"] < quantity:
            raise ValueError("Insufficient stock")

        sku_id = sku_data["id"]
        self.repo.deduct_stock(sku_id, quantity)
        reservation = self.repo.create_reservation(sku_id, quantity, idempotency_key)
        return ReservationResponse(**reservation)

    def confirm_reservation(self, reservation_id: int) -> ConfirmReservationResponse:
        """Confirm a reservation and create an order."""
        reservation = self.repo.get_reservation(reservation_id)
        if reservation is None:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state: {reservation['status']}")

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.now(timezone.utc)
        created_at_utc = created_at.replace(tzinfo=timezone.utc)

        elapsed = (now - created_at_utc).total_seconds()
        if elapsed > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.restore_stock(reservation["sku_id"], reservation["quantity"])
            raise ValueError("Reservation expired")

        self.repo.confirm_reservation(reservation_id)
        self.repo.create_order(reservation_id, reservation["sku_id"], reservation["quantity"])

        updated_reservation = self.repo.get_reservation(reservation_id)
        return ConfirmReservationResponse(
            id=updated_reservation["id"],
            sku=updated_reservation["sku"],
            quantity=updated_reservation["quantity"],
            status=updated_reservation["status"],
            confirmed_at=datetime.fromisoformat(updated_reservation["confirmed_at"]),
        )

    def cancel_reservation(self, reservation_id: int) -> dict:
        """Cancel a reservation and restore stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if reservation is None:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state: {reservation['status']}")

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.restore_stock(reservation["sku_id"], reservation["quantity"])

        return {
            "id": reservation["id"],
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": "CANCELLED",
        }

    def get_orders(self, page: int = 1, size: int = 10) -> PaginatedOrdersResponse:
        """Get paginated orders."""
        if page < 1:
            page = 1
        if size < 1:
            size = 10

        orders, total = self.repo.get_orders(page, size)
        items = [
            OrderResponse(
                id=order["id"],
                sku=order["sku"],
                quantity=order["quantity"],
                created_at=datetime.fromisoformat(order["created_at"]),
            )
            for order in orders
        ]
        return PaginatedOrdersResponse(items=items, page=page, size=size, total=total)
