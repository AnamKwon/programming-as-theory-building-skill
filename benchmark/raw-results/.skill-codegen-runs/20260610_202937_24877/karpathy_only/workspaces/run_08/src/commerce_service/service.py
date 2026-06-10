from datetime import datetime, timezone
from .repository import Repository, SKU, Reservation, Order


class CommerceService:
    RESERVATION_EXPIRATION_SECONDS = 300

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> SKU:
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Reservation:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku_record = self.repo.get_sku_by_sku(sku)
        if not sku_record or sku_record.available_stock < quantity:
            raise ValueError("Insufficient stock")

        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        sku_record.available_stock -= quantity
        sku_record.reserved_stock += quantity
        self.repo.db.commit()

        return reservation

    def confirm_reservation(self, reservation_id: int) -> tuple[Reservation, Order]:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        if reservation.status != "PENDING":
            raise ValueError("Reservation is not in PENDING state")

        now_utc = datetime.now(timezone.utc)
        created_utc = reservation.created_at.replace(tzinfo=timezone.utc)
        elapsed = (now_utc - created_utc).total_seconds()

        if elapsed > self.RESERVATION_EXPIRATION_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            sku_record = self.repo.get_sku_by_sku(reservation.sku)
            if sku_record:
                sku_record.available_stock += reservation.quantity
                sku_record.reserved_stock -= reservation.quantity
                self.repo.db.commit()
            raise ValueError("Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(reservation_id)

        sku_record = self.repo.get_sku_by_sku(reservation.sku)
        if sku_record:
            sku_record.reserved_stock -= reservation.quantity
            self.repo.db.commit()

        return reservation, order

    def cancel_reservation(self, reservation_id: int) -> Reservation:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        if reservation.status != "PENDING":
            raise ValueError("Reservation is not in PENDING state")

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        sku_record = self.repo.get_sku_by_sku(reservation.sku)
        if sku_record:
            sku_record.available_stock += reservation.quantity
            sku_record.reserved_stock -= reservation.quantity
            self.repo.db.commit()

        return reservation
