from datetime import datetime, timezone
from typing import Optional, Tuple, List, Dict
from .repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> Dict:
        sku_id = self.repo.create_sku(sku, initial_stock)
        return {
            "id": sku_id,
            "sku": sku,
            "initial_stock": initial_stock
        }

    def adjust_stock(self, sku: str, amount: int) -> Optional[int]:
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str
    ) -> Tuple[Dict, int]:
        # Check for existing idempotent reservation
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing, 201

        # Check stock availability
        sku_data = self.repo.get_sku_by_name(sku)
        if not sku_data:
            return {"detail": "SKU not found"}, 400

        if sku_data['stock'] < quantity:
            return {"detail": "Insufficient stock"}, 400

        # Deduct stock and create reservation
        self.repo.adjust_stock(sku, -quantity)
        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)

        # Cache the response for idempotency
        self.repo.cache_idempotent_response(idempotency_key, reservation)

        return reservation, 201

    def confirm_reservation(self, reservation_id: int) -> Tuple[Dict, int]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return {"detail": "Reservation not found"}, 404

        if reservation['status'] != "PENDING":
            return {"detail": "Reservation is not in PENDING state"}, 400

        # Check expiration (300 seconds)
        created_at = datetime.fromisoformat(reservation['created_at'])
        now = datetime.now(timezone.utc)
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > 300:
            # Expire the reservation and restore stock
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation['sku'], reservation['quantity'])
            return {"detail": "Reservation expired"}, 400

        # Confirm and create order
        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order_id = self.repo.create_order(reservation_id)

        return {
            "id": reservation_id,
            "status": "CONFIRMED",
            "order_id": order_id
        }, 200

    def cancel_reservation(self, reservation_id: int) -> Tuple[Dict, int]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return {"detail": "Reservation not found"}, 404

        if reservation['status'] != "PENDING":
            return {"detail": "Reservation is not in PENDING state"}, 400

        # Restore stock and cancel
        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.adjust_stock(reservation['sku'], reservation['quantity'])

        return {
            "id": reservation_id,
            "status": "CANCELLED",
            "stock_restored": reservation['quantity']
        }, 200

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> Dict:
        orders, total = self.repo.get_orders_paginated(page, size)
        return {
            "items": orders,
            "page": page,
            "size": size,
            "total": total
        }
