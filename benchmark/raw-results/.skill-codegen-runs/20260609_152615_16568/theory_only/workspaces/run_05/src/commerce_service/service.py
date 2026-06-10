import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from commerce_service.repository import Repository
from commerce_service.models import ReservationState


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class Commerce:
    def __init__(self, db: Session):
        self.repo = Repository(db)
        self.db = db

    def create_sku(self, sku_id: str, name: str, initial_stock: int = 0):
        sku = self.repo.create_sku(sku_id, name)
        if initial_stock >= 0:
            self.repo.create_stock(sku_id, initial_stock)
        return sku

    def adjust_stock(self, sku_id: str, quantity_delta: int):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU not found: {sku_id}")
        stock = self.repo.get_stock(sku_id)
        if stock is None:
            raise ValueError(f"Stock not found for SKU {sku_id}")
        if stock.quantity + quantity_delta < 0:
            raise ValueError(f"Stock adjustment would result in negative quantity")
        return self.repo.update_stock(sku_id, quantity_delta)

    def reserve(self, sku_id: str, quantity: int, idempotency_key: str, ttl_minutes: int = 15) -> dict:
        # Check idempotency: return existing reservation if present
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.state == ReservationState.EXPIRED:
                raise ReservationExpiredError(f"Reservation {existing.id} has expired")
            return {
                "reservation_id": existing.id,
                "sku_id": existing.sku_id,
                "quantity": existing.quantity,
                "state": existing.state,
                "expires_at": existing.expires_at.isoformat(),
                "is_new": False,
            }

        # Validate SKU exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU not found: {sku_id}")

        # Check stock availability
        stock = self.repo.get_stock(sku_id)
        if not stock or stock.quantity < quantity:
            raise InsufficientStockError(f"Insufficient stock for SKU {sku_id}")

        # Create reservation
        reservation_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
        reservation = self.repo.create_reservation(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )

        return {
            "reservation_id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "state": reservation.state,
            "expires_at": reservation.expires_at.isoformat(),
            "is_new": True,
        }

    def confirm_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation not found: {reservation_id}")

        # Check expiration
        now = datetime.now(timezone.utc)
        if now > reservation.expires_at:
            self.repo.update_reservation_state(reservation_id, ReservationState.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        # Check state
        if reservation.state != ReservationState.PENDING:
            raise InvalidStateTransitionError(f"Cannot confirm reservation in state {reservation.state}")

        # Deduct from stock
        stock = self.repo.get_stock(reservation.sku_id)
        if not stock or stock.quantity < reservation.quantity:
            raise InsufficientStockError(f"Insufficient stock to confirm reservation")

        self.repo.update_stock(reservation.sku_id, -reservation.quantity)

        # Update reservation and create order
        now = datetime.now(timezone.utc)
        self.repo.update_reservation_state(reservation_id, ReservationState.CONFIRMED, now)

        order_id = str(uuid.uuid4())
        order = self.repo.create_order(
            order_id=order_id,
            reservation_id=reservation_id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
        )
        self.repo.update_order_state(order_id, ReservationState.CONFIRMED, now)

        return {
            "order_id": order.id,
            "reservation_id": order.reservation_id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "state": order.state,
            "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
        }

    def cancel_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation not found: {reservation_id}")

        if reservation.state in (ReservationState.CANCELLED, ReservationState.CONFIRMED):
            raise InvalidStateTransitionError(
                f"Cannot cancel reservation in state {reservation.state}"
            )

        now = datetime.now(timezone.utc)
        self.repo.update_reservation_state(reservation_id, ReservationState.CANCELLED, now)

        return {
            "reservation_id": reservation.id,
            "state": ReservationState.CANCELLED,
            "cancelled_at": now.isoformat(),
        }
