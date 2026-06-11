"""Business logic layer."""

from datetime import datetime, timedelta
from typing import Optional, Tuple, List

from .repository import Database, SKURepository, ReservationRepository, OrderRepository
from .models import ReservationResponse, OrderResponse


RESERVATION_EXPIRY_SECONDS = 300


class CommerceService:
    """Core business logic for commerce operations."""

    def __init__(self, db: Database):
        self.db = db
        self.sku_repo = SKURepository(db)
        self.reservation_repo = ReservationRepository(db)
        self.order_repo = OrderRepository(db)

    def create_sku(self, sku: str, initial_stock: int) -> Tuple[int, str, int]:
        """Create a new SKU. Returns (id, sku, available_stock)."""
        return self.sku_repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> Optional[int]:
        """
        Adjust stock for a SKU. Returns new stock level or None if SKU not found.
        """
        sku_info = self.sku_repo.get_sku_by_name(sku)
        if not sku_info:
            return None

        sku_id = sku_info[0]
        return self.sku_repo.adjust_stock(sku_id, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Tuple[bool, Optional[ReservationResponse], Optional[str]]:
        """
        Create a reservation with idempotency and stock validation.

        Returns:
            (success: bool, reservation: ReservationResponse or None, error: str or None)
        """
        existing = self.reservation_repo.get_reservation_by_idempotency_key(
            idempotency_key
        )
        if existing:
            res_id, sku_id, qty, status, created_at, idem_key = existing
            sku_info = self.sku_repo.get_sku_by_name(sku)
            sku_name = sku_info[1] if sku_info else sku

            return True, ReservationResponse(
                id=res_id,
                sku=sku_name,
                quantity=qty,
                status=status,
                created_at=created_at,
                idempotency_key=idem_key,
            ), None

        sku_info = self.sku_repo.get_sku_by_name(sku)
        if not sku_info:
            return False, None, "SKU not found"

        sku_id, sku_name, available_stock = sku_info
        if available_stock < quantity:
            return False, None, "Insufficient stock"

        self.sku_repo.adjust_stock(sku_id, -quantity)

        res_id, _, qty, status, created_at, idem_key = (
            self.reservation_repo.create_reservation(sku_id, quantity, idempotency_key)
        )

        return True, ReservationResponse(
            id=res_id,
            sku=sku_name,
            quantity=qty,
            status=status,
            created_at=created_at,
            idempotency_key=idem_key,
        ), None

    def confirm_reservation(self, res_id: int) -> Tuple[bool, Optional[Tuple], Optional[str]]:
        """
        Confirm a reservation and create an order.

        Returns:
            (success: bool, (reservation_id, order_id, status) or None, error: str or None)
        """
        res = self.reservation_repo.get_reservation_by_id(res_id)
        if not res:
            return False, None, "Reservation not found"

        res_id, sku_id, quantity, status, created_at, _ = res

        if status != "PENDING":
            return False, None, f"Reservation is not in PENDING state"

        now = datetime.utcnow()
        elapsed = (now - created_at).total_seconds()

        if elapsed > RESERVATION_EXPIRY_SECONDS:
            self.reservation_repo.update_reservation_status(res_id, "EXPIRED")
            self.sku_repo.adjust_stock(sku_id, quantity)
            return False, None, "Reservation expired"

        self.reservation_repo.update_reservation_status(res_id, "CONFIRMED")
        order_id, _, _ = self.order_repo.create_order(res_id)

        return True, (res_id, order_id, "CONFIRMED"), None

    def cancel_reservation(self, res_id: int) -> Tuple[bool, Optional[Tuple], Optional[str]]:
        """
        Cancel a reservation and restore stock.

        Returns:
            (success: bool, (reservation_id, status, restored_stock) or None, error: str or None)
        """
        res = self.reservation_repo.get_reservation_by_id(res_id)
        if not res:
            return False, None, "Reservation not found"

        res_id, sku_id, quantity, status, _, _ = res

        if status != "PENDING":
            return False, None, f"Reservation is not in PENDING state"

        self.reservation_repo.update_reservation_status(res_id, "CANCELLED")
        self.sku_repo.adjust_stock(sku_id, quantity)

        return True, (res_id, "CANCELLED", quantity), None

    def get_orders_paginated(
        self, page: int = 1, size: int = 10
    ) -> Tuple[List[OrderResponse], int, int]:
        """
        Get paginated orders.

        Returns:
            (orders, total_count, page_count)
        """
        orders, total = self.order_repo.get_orders_paginated(page, size)

        order_responses = [
            OrderResponse(id=order_id, reservation_id=res_id, created_at=created_at)
            for order_id, res_id, created_at in orders
        ]

        page_count = (total + size - 1) // size if total > 0 else 1

        return order_responses, total, page_count
