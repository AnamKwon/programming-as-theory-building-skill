from datetime import datetime, timezone
from .repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock"""
        sku_record = self.repo.create_sku(sku, initial_stock)
        return self._format_sku_response(sku_record)

    def get_sku(self, sku: str) -> dict:
        """Get SKU information"""
        sku_record = self.repo.get_sku(sku)
        if not sku_record:
            return None
        return self._format_sku_response(sku_record)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        """Adjust stock level for a SKU"""
        sku_record = self.repo.adjust_stock(sku, amount)
        if not sku_record:
            return None
        return {
            "sku": sku_record["sku"],
            "available_stock": sku_record["available_stock"]
        }

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        """Create a reservation with idempotency check"""
        # Check if this idempotency key already exists
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return self._format_reservation_response(existing)

        # Check if SKU exists
        sku_record = self.repo.get_sku(sku)
        if not sku_record:
            return None

        # Check available stock
        if sku_record["available_stock"] < quantity:
            raise ValueError("Insufficient stock")

        # Deduct stock
        self.repo.adjust_stock(sku, -quantity)

        # Create reservation
        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        return self._format_reservation_response(reservation)

    def confirm_reservation(self, reservation_id: int) -> dict:
        """Confirm a reservation and create an order"""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return None

        # Check status is PENDING
        if reservation["status"] != "PENDING":
            raise ValueError("Reservation is not in PENDING status")

        # Check expiration (300 seconds)
        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        elapsed = (now - created_at).total_seconds()

        if elapsed > 300:
            # Expire the reservation
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            # Restore stock
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise ValueError("Reservation expired")

        # Update reservation status to CONFIRMED
        confirmed = self.repo.update_reservation_status(reservation_id, "CONFIRMED")

        # Create order
        self.repo.create_order(reservation_id)

        return self._format_reservation_response(confirmed)

    def cancel_reservation(self, reservation_id: int) -> dict:
        """Cancel a reservation and restore stock"""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return None

        # Check status is PENDING
        if reservation["status"] != "PENDING":
            raise ValueError("Reservation is not in PENDING status")

        # Update status to CANCELLED
        cancelled = self.repo.update_reservation_status(reservation_id, "CANCELLED")

        # Restore stock
        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])

        return self._format_reservation_response(cancelled)

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> dict:
        """Get paginated orders"""
        orders, total = self.repo.get_orders_paginated(page, size)
        return {
            "items": [self._format_order_response(order) for order in orders],
            "page": page,
            "size": size,
            "total": total
        }

    def _format_sku_response(self, sku_record: dict) -> dict:
        return {
            "id": sku_record["id"],
            "sku": sku_record["sku"],
            "available_stock": sku_record["available_stock"],
            "created_at": sku_record["created_at"],
            "updated_at": sku_record["updated_at"]
        }

    def _format_reservation_response(self, reservation: dict) -> dict:
        return {
            "id": reservation["id"],
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": reservation["status"],
            "idempotency_key": reservation["idempotency_key"],
            "created_at": reservation["created_at"]
        }

    def _format_order_response(self, order: dict) -> dict:
        return {
            "id": order["id"],
            "reservation_id": order["reservation_id"],
            "created_at": order["created_at"]
        }
