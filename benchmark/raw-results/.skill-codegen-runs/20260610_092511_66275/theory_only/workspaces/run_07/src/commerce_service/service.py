from datetime import datetime, timedelta

from .models import DBOrder, DBReservation, DBSku, DBStock, OrderState, ReservationState
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class CommerceService:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, name: str, price: float) -> DBSku:
        return self.repo.create_sku(sku, name, price)

    def adjust_stock(self, sku_id: int, quantity: int) -> DBStock:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        result = self.repo.adjust_stock(sku_id, quantity)
        if not result:
            raise SKUNotFoundError(f"Stock for SKU {sku_id} not found")
        return result

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str
    ) -> DBReservation:
        # Check idempotency: if key exists, return the existing reservation
        existing_id = self.repo.check_idempotency_key(idempotency_key)
        if existing_id:
            reservation = self.repo.get_reservation(existing_id)
            if reservation:
                return reservation

        # Validate SKU exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        # Check stock availability
        stock = self.repo.get_stock(sku_id)
        if not stock or stock.available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_id}. Available: {stock.available if stock else 0}, Requested: {quantity}"
            )

        # Create reservation
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)
        return self.repo.create_reservation(sku_id, quantity, expires_at, idempotency_key)

    def confirm_reservation(self, reservation_id: int) -> tuple[DBReservation, DBOrder]:
        # Expire any pending reservations first
        self.repo.expire_reservations()

        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Check if reservation is still valid
        if reservation.state == ReservationState.EXPIRED:
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.state == ReservationState.CANCELLED:
            raise ReservationExpiredError(f"Reservation {reservation_id} is cancelled")

        if reservation.state == ReservationState.CONFIRMED:
            # Already confirmed, idempotent response
            order = self.repo.get_orders(limit=1000, offset=0)[0]
            matching_order = next(
                (o for o in order if o.sku_id == reservation.sku_id and o.state == OrderState.CONFIRMED),
                None,
            )
            if matching_order:
                return reservation, matching_order
            # Fall through to create order if not already created

        # Update reservation state
        confirmed = self.repo.confirm_reservation(reservation_id)

        # Create corresponding order
        order = self.repo.create_order(reservation.sku_id, reservation.quantity, OrderState.CONFIRMED)

        return confirmed, order

    def cancel_reservation(self, reservation_id: int) -> DBReservation:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state == ReservationState.CANCELLED:
            # Already cancelled, idempotent response
            return reservation

        return self.repo.cancel_reservation(reservation_id)

    def get_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[DBOrder], int]:
        return self.repo.get_orders(limit, offset)
