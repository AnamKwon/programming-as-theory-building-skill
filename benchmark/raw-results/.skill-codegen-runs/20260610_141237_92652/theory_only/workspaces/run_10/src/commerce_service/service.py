from datetime import datetime, timezone
from commerce_service.repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def create_sku(self, sku: str, initial_stock: int):
        return self.repository.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int):
        result = self.repository.update_stock(sku, amount)
        if not result:
            raise ValueError(f"SKU {sku} not found")
        return result

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str):
        # Check if already reserved with this key (idempotency)
        existing = self.repository.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        # Check stock availability
        sku_obj = self.repository.get_sku(sku)
        if not sku_obj or sku_obj.available_stock < quantity:
            raise ValueError("Insufficient stock")

        # Deduct stock
        self.repository.update_stock(sku, -quantity)

        # Create reservation
        return self.repository.create_reservation(sku, quantity, idempotency_key)

    def confirm_reservation(self, reservation_id: int):
        reservation = self.repository.get_reservation(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        if reservation.status != "PENDING":
            raise ValueError("Reservation is not pending")

        # Check expiration (300 seconds)
        now = datetime.now(timezone.utc)
        created = reservation.created_at.replace(tzinfo=timezone.utc) if reservation.created_at.tzinfo is None else reservation.created_at
        elapsed = (now - created).total_seconds()

        if elapsed > 300:
            # Mark as expired and restore stock
            self.repository.update_reservation_status(reservation_id, "EXPIRED")
            self.repository.update_stock(reservation.sku, reservation.quantity)
            raise ValueError("Reservation expired")

        # Update status to CONFIRMED
        self.repository.update_reservation_status(reservation_id, "CONFIRMED")

        # Create corresponding order
        order = self.repository.create_order(reservation_id)

        return order

    def cancel_reservation(self, reservation_id: int):
        reservation = self.repository.get_reservation(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        if reservation.status != "PENDING":
            raise ValueError("Reservation is not pending")

        # Update status to CANCELLED
        self.repository.update_reservation_status(reservation_id, "CANCELLED")

        # Restore stock
        self.repository.update_stock(reservation.sku, reservation.quantity)

        return reservation

    def list_orders(self, page: int = 1, size: int = 10):
        skip = (page - 1) * size
        orders, total = self.repository.list_orders(skip=skip, limit=size)
        return orders, total, page, size
