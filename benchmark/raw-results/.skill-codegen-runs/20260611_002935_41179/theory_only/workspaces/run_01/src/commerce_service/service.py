"""Business logic service for commerce operations."""

from datetime import datetime
from typing import Optional, Tuple

from .repository import Repository
from .models import ReservationResponse, OrderResponse, OrderListResponse


RESERVATION_EXPIRY_SECONDS = 300


class CommerceService:
    """Service layer for commerce operations."""

    def __init__(self, repo: Optional[Repository] = None):
        self.repo = repo or Repository()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock."""
        self.repo.create_sku(sku, initial_stock)
        return {"sku": sku, "stock": initial_stock}

    def adjust_stock(self, sku: str, amount: int) -> dict:
        """Adjust stock level for a SKU."""
        new_stock = self.repo.update_stock(sku, amount)
        return {"sku": sku, "new_stock": new_stock}

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str
    ) -> Tuple[ReservationResponse, int]:
        """
        Create a reservation with idempotency.
        Returns (reservation_response, status_code).
        Possible status codes: 201 (created), 400 (insufficient stock or existing key).
        """
        # Check for existing reservation with same idempotency key
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return (
                ReservationResponse(
                    id=existing['id'],
                    sku=existing['sku'],
                    quantity=existing['quantity'],
                    status=existing['status'],
                    created_at=existing['created_at']
                ),
                201
            )

        # Check stock availability
        sku_record = self.repo.get_sku(sku)
        if not sku_record or sku_record['stock'] < quantity:
            return (
                {"detail": "Insufficient stock"},
                400
            )

        # Deduct stock and create reservation
        self.repo.update_stock(sku, -quantity)
        now = datetime.utcnow()
        reservation_id = self.repo.create_reservation(sku, quantity, idempotency_key, now)

        reservation = self.repo.get_reservation(reservation_id)
        return (
            ReservationResponse(
                id=reservation['id'],
                sku=reservation['sku'],
                quantity=reservation['quantity'],
                status=reservation['status'],
                created_at=reservation['created_at']
            ),
            201
        )

    def confirm_reservation(self, reservation_id: int) -> Tuple[dict, int]:
        """
        Confirm a reservation and create an order.
        Returns (response, status_code).
        Possible status codes: 200 (success), 400 (invalid state or expired).
        """
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return {"detail": "Reservation not found"}, 404

        # Check status is PENDING
        if reservation['status'] != 'PENDING':
            return {"detail": "Reservation is not in PENDING state"}, 400

        # Check expiration (300 seconds)
        now = datetime.utcnow()
        age_seconds = (now - reservation['created_at']).total_seconds()
        if age_seconds > RESERVATION_EXPIRY_SECONDS:
            # Mark as expired and restore stock
            self.repo.update_reservation_status(reservation_id, 'EXPIRED')
            self.repo.update_stock(reservation['sku'], reservation['quantity'])
            return {"detail": "Reservation expired"}, 400

        # Update reservation status and create order
        self.repo.update_reservation_status(reservation_id, 'CONFIRMED')
        order_id = self.repo.create_order(reservation_id, now)

        return {
            "reservation_id": reservation_id,
            "order_id": order_id,
            "status": "CONFIRMED"
        }, 200

    def cancel_reservation(self, reservation_id: int) -> Tuple[dict, int]:
        """
        Cancel a reservation and restore stock.
        Returns (response, status_code).
        """
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return {"detail": "Reservation not found"}, 404

        # Check status is PENDING
        if reservation['status'] != 'PENDING':
            return {"detail": "Reservation is not in PENDING state"}, 400

        # Update status and restore stock
        self.repo.update_reservation_status(reservation_id, 'CANCELLED')
        self.repo.update_stock(reservation['sku'], reservation['quantity'])

        return {
            "reservation_id": reservation_id,
            "status": "CANCELLED"
        }, 200

    def get_orders(self, page: int = 1, size: int = 10) -> OrderListResponse:
        """Get paginated orders."""
        orders, total = self.repo.get_orders_paginated(page, size)
        return OrderListResponse(
            items=[
                OrderResponse(
                    id=order['id'],
                    reservation_id=order['reservation_id'],
                    created_at=order['created_at']
                )
                for order in orders
            ],
            page=page,
            size=size,
            total=total
        )
