import uuid
from datetime import datetime, timedelta

from .models import ReservationStatus, SKUEntity, ReservationEntity, OrderEntity
from .repository import Repository


class InvalidStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ReservationStatusError(Exception):
    pass


class IdempotencyError(Exception):
    pass


class CommerceService:
    RESERVATION_TTL_MINUTES = 30

    def __init__(self, repository: Repository):
        self.repo = repository

    # ========================================================================
    # SKU Operations
    # ========================================================================

    def create_sku(self, sku_id: str, name: str, quantity_on_hand: float) -> SKUEntity:
        return self.repo.create_sku(sku_id, name, quantity_on_hand)

    def get_sku(self, sku_id: str) -> SKUEntity:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return sku

    def adjust_stock(self, sku_id: str, delta: float) -> SKUEntity:
        sku = self.repo.update_sku_quantity(sku_id, delta)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        if sku.quantity_on_hand < 0:
            raise InvalidStockError(
                f"Insufficient stock for SKU {sku_id} after adjustment"
            )
        return sku

    # ========================================================================
    # Reservation Operations
    # ========================================================================

    def create_reservation(
        self, sku_id: str, quantity: float, idempotency_key: str = None
    ) -> ReservationEntity:
        # Check idempotency: if same key exists, return it (for retries)
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                if existing.status == ReservationStatus.CANCELED:
                    raise IdempotencyError(
                        f"Idempotency key {idempotency_key} was used for a canceled reservation"
                    )
                return existing

        # Validate stock availability: on-hand minus pending reservations
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        reserved = self.repo.get_reserved_quantity(sku_id)
        available = sku.quantity_on_hand - reserved

        if available < quantity:
            raise InvalidStockError(
                f"Insufficient stock for SKU {sku_id}: "
                f"available {available}, requested {quantity}"
            )

        # Create reservation
        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        return self.repo.create_reservation(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

    def get_reservation(self, reservation_id: str) -> ReservationEntity:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")
        return reservation

    def confirm_reservation(
        self, reservation_id: str, idempotency_key: str = None
    ) -> OrderEntity:
        # Check idempotency: if same key exists, return the order
        if idempotency_key:
            existing_order = self.repo.get_order_by_idempotency_key(idempotency_key)
            if existing_order:
                return existing_order

        reservation = self.get_reservation(reservation_id)

        # Check reservation status and expiration
        if reservation.status != ReservationStatus.PENDING:
            raise ReservationStatusError(
                f"Cannot confirm reservation {reservation_id}: "
                f"status is {reservation.status.value}"
            )

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        # Update reservation status and create order
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

        order_id = str(uuid.uuid4())
        order = self.repo.create_order(
            order_id=order_id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            reservation_id=reservation_id,
            idempotency_key=idempotency_key,
        )

        return order

    def cancel_reservation(self, reservation_id: str) -> ReservationEntity:
        reservation = self.get_reservation(reservation_id)

        if reservation.status != ReservationStatus.PENDING:
            raise ReservationStatusError(
                f"Cannot cancel reservation {reservation_id}: "
                f"status is {reservation.status.value}"
            )

        return self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELED)

    # ========================================================================
    # Order Operations
    # ========================================================================

    def get_order(self, order_id: str) -> OrderEntity:
        order = self.repo.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return order

    def list_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[OrderEntity], int]:
        return self.repo.list_orders(page=page, page_size=page_size)
