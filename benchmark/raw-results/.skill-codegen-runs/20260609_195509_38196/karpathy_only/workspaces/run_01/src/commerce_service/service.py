"""Business logic layer."""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .models import ReservationModel, OrderModel
from .repository import SKURepository, ReservationRepository, OrderRepository


class InsufficientStockError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class IdempotencyViolationError(Exception):
    pass


class CommerceService:
    def __init__(self, db: Session):
        self.db = db
        self.sku_repo = SKURepository(db)
        self.reservation_repo = ReservationRepository(db)
        self.order_repo = OrderRepository(db)

    def create_sku(self, name: str, quantity_available: float):
        return self.sku_repo.create(name, quantity_available)

    def adjust_stock(self, sku_id: int, delta: float):
        sku = self.sku_repo.update_quantity(sku_id, delta)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return sku

    def reserve_inventory(
        self, sku_id: int, quantity: float, idempotency_key: str, ttl_seconds: int
    ) -> ReservationModel:
        # Check for existing reservation with same idempotency key
        existing = self.reservation_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == "cancelled":
                raise IdempotencyViolationError(
                    "Idempotency key already used for cancelled reservation"
                )
            return existing

        # Check stock availability
        sku = self.sku_repo.get_by_id(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        # Calculate reserved quantity from active pending reservations
        active_reservations = self.reservation_repo.get_active_by_sku(sku_id)
        reserved_qty = sum(r.quantity for r in active_reservations)
        available = sku.quantity_available - reserved_qty

        if available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock. Available: {available}, Requested: {quantity}"
            )

        # Create reservation
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        reservation = self.reservation_repo.create(
            sku_id, quantity, idempotency_key, expires_at
        )

        # Create corresponding order in reserved status
        self.order_repo.create(sku_id, quantity, status="reserved")

        return reservation

    def confirm_reservation(self, reservation_id: int) -> ReservationModel:
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "pending":
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in {reservation.status} state"
            )

        if reservation.expires_at < datetime.utcnow():
            raise ReservationExpiredError("Reservation has expired")

        # Update reservation status
        reservation = self.reservation_repo.update_status(reservation_id, "confirmed")

        # Reduce inventory
        self.sku_repo.update_quantity(reservation.sku_id, -reservation.quantity)

        return reservation

    def cancel_reservation(self, reservation_id: int) -> ReservationModel:
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status == "cancelled":
            return reservation

        if reservation.status not in ("pending", "confirmed"):
            raise InvalidStateTransitionError(
                f"Cannot cancel reservation in {reservation.status} state"
            )

        # Update reservation status
        reservation = self.reservation_repo.update_status(reservation_id, "cancelled")

        # If it was confirmed, we need to release inventory back
        if reservation.status == "confirmed":
            self.sku_repo.update_quantity(reservation.sku_id, reservation.quantity)

        return reservation

    def get_orders(self, limit: int = 10, offset: int = 0):
        return self.order_repo.list_orders(limit, offset)
