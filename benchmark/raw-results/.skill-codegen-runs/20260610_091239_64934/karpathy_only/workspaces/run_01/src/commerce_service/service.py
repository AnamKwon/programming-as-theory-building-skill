"""Business logic for the commerce service."""

from datetime import datetime, timedelta

from fastapi import HTTPException, status

from .models import OrderStatus, ReservationStatus
from .repository import Repository


class CommerceService:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, name: str, price: float) -> dict:
        try:
            sku_id = self.repo.create_sku(name, price)
            return {"id": sku_id, "name": name, "price": price}
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    def adjust_stock(self, sku_id: int, quantity: int) -> dict:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )

        self.repo.adjust_stock(sku_id, quantity)
        stock = self.repo.get_stock(sku_id)
        return {
            "sku_id": sku_id,
            "available_quantity": stock["available_quantity"],
            "reserved_quantity": stock["reserved_quantity"],
        }

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
    ) -> dict:
        # Check for existing idempotent request
        existing = self.repo.find_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return self._format_reservation(existing)

        # Verify SKU exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )

        # Check stock availability
        stock = self.repo.get_stock(sku_id)
        available = stock["available_quantity"] - stock["reserved_quantity"]
        if available < quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Insufficient stock available",
            )

        # Create reservation
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)
        reservation_id = self.repo.create_reservation(
            sku_id,
            quantity,
            idempotency_key,
            expires_at,
        )

        reservation = self.repo.get_reservation(reservation_id)
        return self._format_reservation(reservation)

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation["status"] != ReservationStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot confirm reservation in {reservation['status']} status",
            )

        # Check expiration
        expires_at = datetime.fromisoformat(reservation["expires_at"])
        if datetime.utcnow() > expires_at:
            # Mark as expired
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reservation has expired",
            )

        # Confirm the reservation (deduct from available)
        self.repo.update_reservation_status_and_stock(
            reservation_id,
            ReservationStatus.CONFIRMED,
            reservation["sku_id"],
            reservation["quantity"],
        )

        # Create associated order
        self.repo.create_order(
            reservation_id,
            reservation["sku_id"],
            reservation["quantity"],
            OrderStatus.CONFIRMED,
        )

        updated = self.repo.get_reservation(reservation_id)
        return self._format_reservation(updated)

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation["status"] in (ReservationStatus.CANCELLED, ReservationStatus.EXPIRED):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot cancel reservation in {reservation['status']} status",
            )

        # Release the reservation
        self.repo.update_reservation_status_and_stock(
            reservation_id,
            ReservationStatus.CANCELLED,
            reservation["sku_id"],
            reservation["quantity"],
        )

        updated = self.repo.get_reservation(reservation_id)
        return self._format_reservation(updated)

    def list_orders(self, skip: int = 0, limit: int = 20) -> dict:
        orders, total = self.repo.list_orders(skip=skip, limit=limit)
        return {
            "items": [self._format_order(order) for order in orders],
            "total": total,
        }

    def _format_reservation(self, row: dict) -> dict:
        return {
            "id": row["id"],
            "sku_id": row["sku_id"],
            "quantity": row["quantity"],
            "status": row["status"],
            "expires_at": row["expires_at"],
        }

    def _format_order(self, row: dict) -> dict:
        return {
            "id": row["id"],
            "reservation_id": row["reservation_id"],
            "sku_id": row["sku_id"],
            "quantity": row["quantity"],
            "status": row["status"],
            "created_at": row["created_at"],
        }
