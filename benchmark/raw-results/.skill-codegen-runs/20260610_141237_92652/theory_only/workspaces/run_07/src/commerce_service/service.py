"""Business logic layer."""

from datetime import datetime, timedelta
from typing import Optional, Tuple

from .models import ReservationStatus, ReservationResponse, OrderResponse, OrderListResponse
from .repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU."""
        existing = self.repo.get_sku_by_name(sku)
        if existing:
            return {"error": "SKU already exists"}

        sku_obj = self.repo.create_sku(sku, initial_stock)
        return {
            "id": sku_obj.id,
            "sku": sku_obj.sku,
            "available_stock": sku_obj.available_stock,
        }

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        """Adjust stock for a SKU."""
        sku_obj = self.repo.get_sku_by_name(sku)
        if not sku_obj:
            return None

        updated_stock = self.repo.adjust_stock(sku, amount)
        return {
            "sku": sku,
            "available_stock": updated_stock,
        }

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Tuple[Optional[ReservationResponse], Optional[str]]:
        """Create a reservation, ensuring stock availability and idempotency."""
        # Check if reservation already exists (idempotency)
        existing_reservation = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing_reservation:
            return (
                ReservationResponse(
                    id=existing_reservation.id,
                    sku=existing_reservation.sku,
                    quantity=existing_reservation.quantity,
                    status=existing_reservation.status,
                    created_at=existing_reservation.created_at,
                ),
                None,
            )

        # Check if SKU exists and has enough stock
        sku_obj = self.repo.get_sku_by_name(sku)
        if not sku_obj:
            return None, "SKU not found"

        if sku_obj.available_stock < quantity:
            return None, "Insufficient stock"

        # Deduct stock and create reservation
        self.repo.deduct_stock(sku_obj.id, quantity)
        reservation = self.repo.create_reservation(sku, sku_obj.id, quantity, idempotency_key)

        return (
            ReservationResponse(
                id=reservation.id,
                sku=reservation.sku,
                quantity=reservation.quantity,
                status=reservation.status,
                created_at=reservation.created_at,
            ),
            None,
        )

    def confirm_reservation(self, reservation_id: int) -> Tuple[Optional[dict], Optional[str]]:
        """Confirm a pending reservation and create an order."""
        reservation = self.repo.get_reservation(reservation_id)

        if not reservation:
            return None, "Reservation not found"

        if reservation.status != ReservationStatus.PENDING:
            return None, f"Reservation is not in PENDING state"

        # Check expiration (300 seconds)
        now = datetime.utcnow()
        age_seconds = (now - reservation.created_at).total_seconds()

        if age_seconds > 300:
            # Mark as expired and restore stock
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            sku_obj = self.repo.get_sku_by_name(reservation.sku)
            if sku_obj:
                self.repo.restore_stock(sku_obj.id, reservation.quantity)
            return None, "Reservation expired"

        # Update status to CONFIRMED
        updated_reservation = self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED
        )

        # Create order
        order = self.repo.create_order(reservation_id)

        return (
            {
                "reservation_id": reservation_id,
                "order_id": order.id,
                "status": ReservationStatus.CONFIRMED,
            },
            None,
        )

    def cancel_reservation(self, reservation_id: int) -> Tuple[Optional[dict], Optional[str]]:
        """Cancel a pending reservation and restore stock."""
        reservation = self.repo.get_reservation(reservation_id)

        if not reservation:
            return None, "Reservation not found"

        if reservation.status != ReservationStatus.PENDING:
            return None, "Reservation is not in PENDING state"

        # Update status to CANCELLED
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

        # Restore stock
        sku_obj = self.repo.get_sku_by_name(reservation.sku)
        if sku_obj:
            self.repo.restore_stock(sku_obj.id, reservation.quantity)

        return (
            {
                "reservation_id": reservation_id,
                "status": ReservationStatus.CANCELLED,
            },
            None,
        )

    def get_orders(self, page: int = 1, size: int = 10) -> OrderListResponse:
        """Get paginated list of orders."""
        orders, total = self.repo.get_orders(page, size)
        return OrderListResponse(
            page=page,
            size=size,
            total=total,
            orders=[
                OrderResponse(
                    id=order.id,
                    reservation_id=order.reservation_id,
                    created_at=order.created_at,
                )
                for order in orders
            ],
        )
