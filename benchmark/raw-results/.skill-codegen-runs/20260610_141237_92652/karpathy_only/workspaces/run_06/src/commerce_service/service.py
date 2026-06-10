from datetime import datetime, timedelta
from typing import Optional, Tuple

from .repository import Repository, ReservationRecord, OrderRecord, SKURecord


class CommerceService:
    RESERVATION_EXPIRY_SECONDS = 300

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> SKURecord:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> Optional[int]:
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> Tuple[Optional[ReservationRecord], str]:
        """
        Create a reservation. Returns (reservation, status) where status is:
        - 'created': new reservation created
        - 'idempotent': existing reservation with same key returned
        - 'insufficient_stock': not enough stock available
        """
        sku_record = self.repo.get_sku(sku)
        if not sku_record:
            return None, "sku_not_found"

        if sku_record.available_stock < quantity:
            return None, "insufficient_stock"

        reservation, is_idempotent = self.repo.create_reservation(sku, quantity, idempotency_key)

        if is_idempotent:
            return reservation, "idempotent"
        else:
            return reservation, "created"

    def confirm_reservation(self, reservation_id: int) -> Tuple[Optional[OrderRecord], Optional[str]]:
        """
        Confirm a reservation. Returns (order, error) where error is:
        - None: success
        - 'not_found': reservation doesn't exist
        - 'not_pending': reservation is not in PENDING state
        - 'expired': reservation has expired
        """
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return None, "not_found"

        if reservation.status != "PENDING":
            return None, "not_pending"

        now = datetime.utcnow()
        created_at = reservation.created_at
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > self.RESERVATION_EXPIRY_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.restore_stock(reservation_id)
            return None, "expired"

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(reservation_id)
        return order, None

    def cancel_reservation(self, reservation_id: int) -> Tuple[bool, Optional[str]]:
        """
        Cancel a reservation. Returns (success, error) where error is:
        - None: success
        - 'not_found': reservation doesn't exist
        - 'not_pending': reservation is not in PENDING state
        """
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return False, "not_found"

        if reservation.status != "PENDING":
            return False, "not_pending"

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.restore_stock(reservation_id)
        return True, None

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[list[OrderRecord], int]:
        return self.repo.get_orders(page, size)
