from datetime import datetime
from fastapi import HTTPException, status
from .repository import Repository


class CommerceService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku: str, name: str, initial_stock: int) -> dict:
        """Create a new SKU. Raises 409 if SKU already exists."""
        existing = self.repo.get_sku(sku)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"SKU '{sku}' already exists",
            )
        return self.repo.create_sku(sku, name, initial_stock)

    def adjust_stock(self, sku: str, delta: int) -> dict:
        """Adjust stock for a SKU. Raises 404 if SKU not found, 400 if adjustment would go negative."""
        sku_data = self.repo.get_sku(sku)
        if not sku_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU '{sku}' not found",
            )

        if sku_data["stock"] + delta < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Adjustment would result in negative stock",
            )

        return self.repo.adjust_stock(sku, delta)

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str, ttl_seconds: int) -> dict:
        """Create a reservation. Idempotency key ensures repeated calls return same result.
        Raises 404 if SKU not found, 409 if insufficient stock, 409 if key already used."""
        # Check idempotency key
        existing_key = self.repo.get_idempotency_key(idempotency_key)
        if existing_key:
            # Return existing reservation
            res_id = existing_key["reservation_id"]
            res = self.repo.get_reservation(res_id)
            if res:
                return res
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Idempotency key exists but reservation not found",
            )

        # Check SKU exists and has stock
        sku_data = self.repo.get_sku(sku)
        if not sku_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU '{sku}' not found",
            )

        if sku_data["stock"] < quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Insufficient stock for SKU '{sku}'. Available: {sku_data['stock']}, requested: {quantity}",
            )

        # Create reservation and record idempotency key
        res = self.repo.create_reservation(sku, quantity, ttl_seconds)
        self.repo.record_idempotency_key(idempotency_key, res["id"])

        # Reduce available stock
        self.repo.adjust_stock(sku, -quantity)

        return res

    def confirm_reservation(self, res_id: str, idempotency_key: str) -> dict:
        """Confirm a reservation, converting it to an order. Idempotent via key."""
        # Check idempotency key for this specific confirm
        existing_key = self.repo.get_idempotency_key(idempotency_key)
        if existing_key:
            # Key already used, return existing order
            order_res = self.repo.list_orders(limit=1000)
            for order in order_res["items"]:
                if order["reservation_id"] == res_id:
                    return order
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Idempotency key exists but order not found",
            )

        # Get reservation
        res = self.repo.get_reservation(res_id)
        if not res:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation '{res_id}' not found",
            )

        # Check if expired
        expires_at = datetime.fromisoformat(res["expires_at"])
        if datetime.utcnow() > expires_at:
            self.repo.update_reservation_state(res_id, "expired")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reservation has expired",
            )

        # Check state
        if res["state"] == "confirmed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reservation already confirmed",
            )
        if res["state"] == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reservation is cancelled",
            )

        # Create order and mark reservation as confirmed
        order = self.repo.create_order(res_id, res["sku"], res["quantity"])
        self.repo.update_reservation_state(res_id, "confirmed")
        self.repo.record_idempotency_key(idempotency_key, res_id)

        return order

    def cancel_reservation(self, res_id: str) -> dict:
        """Cancel a reservation and restore stock."""
        res = self.repo.get_reservation(res_id)
        if not res:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation '{res_id}' not found",
            )

        if res["state"] in ("cancelled", "confirmed"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot cancel reservation in '{res['state']}' state",
            )

        # Restore stock and mark cancelled
        self.repo.adjust_stock(res["sku"], res["quantity"])
        self.repo.update_reservation_state(res_id, "cancelled")

        return {"message": "Reservation cancelled", "reservation_id": res_id}

    def get_order(self, order_id: str) -> dict:
        """Get order details."""
        order = self.repo.get_order(order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order '{order_id}' not found",
            )
        return order

    def list_orders(self, offset: int = 0, limit: int = 10) -> dict:
        """List orders with pagination."""
        if limit < 1 or limit > 100:
            limit = 10
        if offset < 0:
            offset = 0
        return self.repo.list_orders(offset, limit)
