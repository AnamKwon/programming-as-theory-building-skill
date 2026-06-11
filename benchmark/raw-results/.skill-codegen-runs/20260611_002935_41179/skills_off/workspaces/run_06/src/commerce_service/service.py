"""Business logic service layer."""

from datetime import datetime
from typing import Optional
from .repository import Repository
from .models import ReservationResponse, ConfirmReservationResponse


RESERVATION_EXPIRATION_SECONDS = 300


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock."""
        sku_id = self.repo.create_sku(sku, initial_stock)
        return {"id": sku_id, "sku": sku, "available_stock": initial_stock}

    def adjust_stock(self, sku: str, amount: int) -> dict:
        """Adjust stock level for a SKU."""
        sku_info = self.repo.get_sku_by_name(sku)
        if not sku_info:
            raise ValueError(f"SKU not found: {sku}")

        new_stock = self.repo.adjust_stock(sku, amount)
        return {"sku": sku, "new_stock": new_stock}

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> ReservationResponse:
        """Create a reservation with stock deduction and idempotency check."""
        existing_reservation = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing_reservation:
            return ReservationResponse(
                id=existing_reservation["id"],
                sku=existing_reservation["sku"],
                quantity=existing_reservation["quantity"],
                status=existing_reservation["status"],
                created_at=existing_reservation["created_at"],
                idempotency_key=existing_reservation["idempotency_key"],
            )

        sku_info = self.repo.get_sku_by_name(sku)
        if not sku_info:
            raise ValueError(f"SKU not found: {sku}")

        if sku_info["available_stock"] < quantity:
            raise ValueError("Insufficient stock")

        reservation_data = self.repo.create_reservation(
            sku_info["id"], sku, quantity, idempotency_key
        )

        return ReservationResponse(
            id=reservation_data["id"],
            sku=reservation_data["sku"],
            quantity=reservation_data["quantity"],
            status=reservation_data["status"],
            created_at=reservation_data["created_at"],
            idempotency_key=reservation_data["idempotency_key"],
        )

    def confirm_reservation(self, reservation_id: int) -> ConfirmReservationResponse:
        """Confirm a pending reservation and create an order."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not PENDING: {reservation['status']}")

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > RESERVATION_EXPIRATION_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.restore_stock(reservation["sku_id"], reservation["quantity"])
            raise ValueError("Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order_id = self.repo.create_order(reservation_id)

        return ConfirmReservationResponse(
            id=reservation["id"],
            sku=reservation["sku"],
            quantity=reservation["quantity"],
            status="CONFIRMED",
            created_at=reservation["created_at"],
            order_id=order_id,
        )

    def cancel_reservation(self, reservation_id: int) -> dict:
        """Cancel a reservation and restore stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not PENDING: {reservation['status']}")

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.restore_stock(reservation["sku_id"], reservation["quantity"])

        return {
            "id": reservation["id"],
            "sku": reservation["sku"],
            "status": "CANCELLED",
        }

    def list_orders(self, page: int = 1, size: int = 10) -> dict:
        """List orders with pagination."""
        orders, total = self.repo.list_orders(page, size)
        return {
            "items": orders,
            "page": page,
            "size": size,
            "total": total,
        }
