from datetime import datetime, timezone
from fastapi import HTTPException
from commerce_service.repository import SKURepository, ReservationRepository, OrderRepository


RESERVATION_EXPIRY_SECONDS = 300


class CommerceService:
    def __init__(self):
        self.sku_repo = SKURepository()
        self.reservation_repo = ReservationRepository()
        self.order_repo = OrderRepository()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        sku_data = self.sku_repo.get_sku_by_name(sku)
        if sku_data:
            raise HTTPException(status_code=400, detail="SKU already exists")

        sku_id = self.sku_repo.create_sku(sku, initial_stock)
        return self.sku_repo.get_sku_by_id(sku_id)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        sku_data = self.sku_repo.get_sku_by_name(sku)
        if not sku_data:
            raise HTTPException(status_code=404, detail="SKU not found")

        new_stock = sku_data["available_stock"] + amount
        if new_stock < 0:
            raise HTTPException(status_code=400, detail="Stock cannot be negative")

        self.sku_repo.update_stock(sku_data["id"], new_stock)
        return {"sku": sku, "updated_stock": new_stock}

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        # Check idempotency
        existing = self.reservation_repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return {
                "id": existing["id"],
                "sku": existing["sku"],
                "quantity": existing["quantity"],
                "status": existing["status"],
                "created_at": existing["created_at"],
                "idempotency_key": existing["idempotency_key"],
            }

        # Check stock
        sku_data = self.sku_repo.get_sku_by_name(sku)
        if not sku_data:
            raise HTTPException(status_code=404, detail="SKU not found")

        if sku_data["available_stock"] < quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")

        # Deduct stock
        new_stock = sku_data["available_stock"] - quantity
        self.sku_repo.update_stock(sku_data["id"], new_stock)

        # Create reservation
        now = datetime.now(timezone.utc).isoformat()
        reservation_id = self.reservation_repo.create_reservation(
            sku_data["id"], sku, quantity, idempotency_key, now
        )

        return {
            "id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "status": "PENDING",
            "created_at": now,
            "idempotency_key": idempotency_key,
        }

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.reservation_repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation["status"] != "PENDING":
            raise HTTPException(status_code=400, detail="Reservation is not pending")

        # Check expiration
        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.now(timezone.utc)
        age_seconds = (now - created_at.replace(tzinfo=timezone.utc)).total_seconds()

        if age_seconds > RESERVATION_EXPIRY_SECONDS:
            # Mark as expired
            self.reservation_repo.update_reservation_status(reservation_id, "EXPIRED")
            # Restore stock
            sku_data = self.sku_repo.get_sku_by_name(reservation["sku"])
            self.sku_repo.update_stock(sku_data["id"], sku_data["available_stock"] + reservation["quantity"])
            raise HTTPException(status_code=400, detail="Reservation expired")

        # Confirm and create order
        self.reservation_repo.update_reservation_status(reservation_id, "CONFIRMED")
        now_str = datetime.now(timezone.utc).isoformat()
        order_id = self.order_repo.create_order(reservation_id, now_str)

        return {
            "id": reservation_id,
            "status": "CONFIRMED",
            "order_id": order_id,
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.reservation_repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation["status"] != "PENDING":
            raise HTTPException(status_code=400, detail="Reservation is not pending")

        # Mark as cancelled
        self.reservation_repo.update_reservation_status(reservation_id, "CANCELLED")

        # Restore stock
        sku_data = self.sku_repo.get_sku_by_name(reservation["sku"])
        new_stock = sku_data["available_stock"] + reservation["quantity"]
        self.sku_repo.update_stock(sku_data["id"], new_stock)

        return {
            "id": reservation_id,
            "status": "CANCELLED",
            "restored_stock": new_stock,
        }

    def get_orders(self, page: int, size: int) -> dict:
        if page < 1:
            raise HTTPException(status_code=400, detail="Page must be >= 1")
        if size < 1:
            raise HTTPException(status_code=400, detail="Size must be >= 1")

        orders, total = self.order_repo.get_orders(page, size)

        return {
            "page": page,
            "size": size,
            "total": total,
            "orders": orders,
        }
