from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from commerce_service.repository import Repository, SKU, Reservation, Order


class CommerceService:
    def __init__(self, db: Session):
        self.repo = Repository(db)

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> int:
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> tuple[Reservation, int]:
        db_sku = self.repo.get_sku_by_sku_str(sku)
        if not db_sku:
            raise ValueError(f"SKU {sku} not found")

        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing, 200

        available_stock = self.repo.get_available_stock(db_sku.id)
        if available_stock < quantity:
            raise ValueError("Insufficient stock")

        self.repo.deduct_stock(db_sku.id, quantity)
        reservation = self.repo.create_reservation(db_sku.id, quantity, idempotency_key)
        return reservation, 201

    def confirm_reservation(self, reservation_id: int) -> Reservation:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state")

        created_at = reservation.created_at
        now = datetime.utcnow()
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.restore_stock(reservation.sku_id, reservation.quantity)
            raise ValueError("Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        self.repo.create_order(reservation_id)
        return self.repo.get_reservation_by_id(reservation_id)

    def cancel_reservation(self, reservation_id: int) -> Reservation:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state")

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.restore_stock(reservation.sku_id, reservation.quantity)
        return self.repo.get_reservation_by_id(reservation_id)

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[Order], int]:
        offset = (page - 1) * size
        return self.repo.get_orders(offset, size)
