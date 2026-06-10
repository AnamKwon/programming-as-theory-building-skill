from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from .repository import Repository
from .models import Reservation, Order, SKU

class CommerceService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = Repository(db)

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock."""
        try:
            sku_obj = self.repo.create_sku(sku, initial_stock)
            return {
                "id": sku_obj.id,
                "sku": sku_obj.sku,
                "available_stock": sku_obj.available_stock
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create SKU"
            )

    def adjust_stock(self, sku: str, amount: int) -> dict:
        """Adjust stock level for a SKU."""
        sku_obj = self.repo.get_sku_by_code(sku)
        if not sku_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found"
            )

        sku_obj = self.repo.adjust_stock(sku, amount)
        return {
            "sku": sku_obj.sku,
            "available_stock": sku_obj.available_stock
        }

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> tuple[dict, int]:
        """
        Create a stock reservation with idempotency.
        Returns (response_dict, status_code).
        """
        existing_reservation = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing_reservation:
            return {
                "id": existing_reservation.id,
                "sku": existing_reservation.sku.sku,
                "quantity": existing_reservation.quantity,
                "status": existing_reservation.status,
                "created_at": existing_reservation.created_at.isoformat()
            }, 201

        sku_obj = self.repo.get_sku_by_code(sku)
        if not sku_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found"
            )

        if sku_obj.available_stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock"
            )

        self.repo.deduct_stock(sku_obj.id, quantity)
        reservation = self.repo.create_reservation(sku_obj.id, quantity, idempotency_key)

        return {
            "id": reservation.id,
            "sku": reservation.sku.sku,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "created_at": reservation.created_at.isoformat()
        }, 201

    def confirm_reservation(self, reservation_id: int) -> dict:
        """Confirm a reservation and create an order."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found"
            )

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not PENDING"
            )

        now = datetime.now(timezone.utc)
        created_at = reservation.created_at.replace(tzinfo=timezone.utc)
        elapsed = (now - created_at).total_seconds()

        if elapsed > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.restore_stock(reservation.sku_id, reservation.quantity)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired"
            )

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(reservation_id)

        return {
            "id": order.id,
            "reservation_id": order.reservation_id,
            "created_at": order.created_at.isoformat()
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        """Cancel a reservation and restore stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found"
            )

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not PENDING"
            )

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.restore_stock(reservation.sku_id, reservation.quantity)

        return {
            "id": reservation.id,
            "status": "CANCELLED",
            "restored_quantity": reservation.quantity
        }

    def list_orders(self, page: int = 1, size: int = 10) -> dict:
        """List orders with pagination."""
        if page < 1:
            page = 1
        if size < 1:
            size = 10

        orders, total = self.repo.list_orders(page, size)
        return {
            "items": [
                {
                    "id": order.id,
                    "reservation_id": order.reservation_id,
                    "created_at": order.created_at.isoformat()
                }
                for order in orders
            ],
            "page": page,
            "size": size,
            "total": total
        }
