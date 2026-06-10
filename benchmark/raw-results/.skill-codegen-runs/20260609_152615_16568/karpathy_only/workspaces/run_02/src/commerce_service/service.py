from datetime import datetime
from fastapi import HTTPException
from .repository import SKURepository, ReservationRepository, OrderRepository


class InsufficientStockError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class SKUService:
    @staticmethod
    def create_sku(sku_id: str, stock: int) -> dict:
        existing = SKURepository.get(sku_id)
        if existing:
            raise HTTPException(status_code=409, detail="SKU already exists")
        return SKURepository.create(sku_id, stock)

    @staticmethod
    def adjust_stock(sku_id: str, delta: int) -> dict:
        sku = SKURepository.get(sku_id)
        if not sku:
            raise HTTPException(status_code=404, detail="SKU not found")
        if sku["stock"] + delta < 0:
            raise HTTPException(status_code=400, detail="Insufficient stock for adjustment")
        return SKURepository.adjust_stock(sku_id, delta)


class ReservationService:
    @staticmethod
    def create_reservation(sku_id: str, quantity: int, idempotency_key: str) -> dict:
        existing_res = ReservationRepository.get_by_idempotency_key(idempotency_key)
        if existing_res:
            if existing_res["status"] == "pending":
                expires_at = existing_res["expires_at"]
                if datetime.fromisoformat(expires_at) < datetime.utcnow():
                    raise HTTPException(status_code=410, detail="Reservation expired")
            return {
                "reservation_id": existing_res["reservation_id"],
                "sku_id": existing_res["sku_id"],
                "quantity": existing_res["quantity"],
                "status": existing_res["status"],
                "expires_at": existing_res["expires_at"],
            }

        sku = SKURepository.get(sku_id)
        if not sku:
            raise HTTPException(status_code=404, detail="SKU not found")

        reserved_qty = ReservationRepository.count_active_by_sku(sku_id)
        available = sku["stock"] - reserved_qty

        if available < quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock. Available: {available}, Requested: {quantity}",
            )

        return ReservationRepository.create(sku_id, quantity, idempotency_key)

    @staticmethod
    def confirm_reservation(reservation_id: str) -> dict:
        reservation = ReservationRepository.get(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation["status"] != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot confirm reservation with status: {reservation['status']}",
            )

        expires_at = datetime.fromisoformat(reservation["expires_at"])
        if expires_at < datetime.utcnow():
            ReservationRepository.update_status(reservation_id, "expired")
            raise HTTPException(status_code=410, detail="Reservation expired")

        ReservationRepository.update_status(reservation_id, "confirmed")
        order = OrderRepository.create(
            reservation_id,
            reservation["sku_id"],
            reservation["quantity"],
        )
        OrderRepository.update_status(order["order_id"], "confirmed")

        return {
            "reservation_id": reservation_id,
            "sku_id": reservation["sku_id"],
            "quantity": reservation["quantity"],
            "status": "confirmed",
            "expires_at": reservation["expires_at"],
        }

    @staticmethod
    def cancel_reservation(reservation_id: str) -> dict:
        reservation = ReservationRepository.get(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation["status"] not in ("pending", "confirmed"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel reservation with status: {reservation['status']}",
            )

        ReservationRepository.update_status(reservation_id, "cancelled")

        return {
            "reservation_id": reservation_id,
            "sku_id": reservation["sku_id"],
            "quantity": reservation["quantity"],
            "status": "cancelled",
            "expires_at": reservation["expires_at"],
        }
