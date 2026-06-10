import uuid
from datetime import datetime, timedelta
from commerce_service.models import ReservationState, OrderState
from commerce_service.repository import Repository


class ServiceError(Exception):
    pass


class InsufficientStockError(ServiceError):
    pass


class ReservationExpiredError(ServiceError):
    pass


class ReservationNotFoundError(ServiceError):
    pass


class InvalidStateTransitionError(ServiceError):
    pass


class Service:
    RESERVATION_EXPIRATION_MINUTES = 15

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, code: str, name: str, initial_stock: int = 0) -> dict:
        sku = self.repo.create_sku(str(uuid.uuid4()), code, name, initial_stock)
        return {
            "id": sku.id,
            "code": sku.code,
            "name": sku.name,
            "available_stock": sku.available_stock,
            "created_at": sku.created_at,
        }

    def adjust_stock(self, sku_code: str, quantity: int) -> dict:
        sku = self.repo.adjust_stock(sku_code, quantity)
        return {
            "id": sku.id,
            "code": sku.code,
            "name": sku.name,
            "available_stock": sku.available_stock,
            "created_at": sku.created_at,
        }

    def create_reservation(
        self, sku_code: str, quantity: int, idempotency_key: str
    ) -> dict:
        # Check idempotency
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return self._format_reservation(existing)

        # Verify SKU exists and has stock
        sku = self.repo.get_sku_by_code(sku_code)
        if not sku:
            raise ServiceError(f"SKU {sku_code} not found")

        # Calculate available stock (total - pending reservations)
        pending = self.repo.get_pending_reservations_for_sku(sku_code)
        reserved_qty = sum(r.quantity for r in pending)
        available = sku.available_stock - reserved_qty

        if available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku_code}: requested {quantity}, available {available}"
            )

        # Create reservation
        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_EXPIRATION_MINUTES)
        reservation = self.repo.create_reservation(
            reservation_id, sku_code, quantity, expires_at, idempotency_key
        )
        return self._format_reservation(reservation)

    def confirm_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state != ReservationState.PENDING:
            raise InvalidStateTransitionError(
                f"Reservation {reservation_id} is in state {reservation.state}, cannot confirm"
            )

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_state(reservation_id, ReservationState.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        # Deduct from available stock
        self.repo.adjust_stock(reservation.sku_code, -reservation.quantity)

        # Mark as confirmed
        updated = self.repo.update_reservation_state(reservation_id, ReservationState.CONFIRMED)
        return self._format_reservation(updated)

    def cancel_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state == ReservationState.CONFIRMED:
            self.repo.adjust_stock(reservation.sku_code, reservation.quantity)
        elif reservation.state not in (ReservationState.PENDING, ReservationState.EXPIRED):
            raise InvalidStateTransitionError(
                f"Cannot cancel reservation in state {reservation.state}"
            )

        updated = self.repo.update_reservation_state(reservation_id, ReservationState.CANCELLED)
        return self._format_reservation(updated)

    def create_order(self, reservation_ids: list[str] | None = None) -> dict:
        order_id = str(uuid.uuid4())
        order = self.repo.create_order(order_id)

        if reservation_ids:
            for res_id in reservation_ids:
                self.repo.add_reservation_to_order(order_id, res_id, str(uuid.uuid4()))

        reservations = self.repo.get_reservations_for_order(order_id)
        return {
            "id": order.id,
            "state": order.state.value,
            "reservation_ids": [r.id for r in reservations],
            "created_at": order.created_at,
        }

    def get_order(self, order_id: str) -> dict:
        order = self.repo.get_order_by_id(order_id)
        if not order:
            raise ServiceError(f"Order {order_id} not found")
        reservations = self.repo.get_reservations_for_order(order_id)
        return {
            "id": order.id,
            "state": order.state.value,
            "reservation_ids": [r.id for r in reservations],
            "created_at": order.created_at,
        }

    def list_orders(self, page: int = 1, page_size: int = 10) -> dict:
        offset = (page - 1) * page_size
        orders, total = self.repo.list_orders(offset, page_size)
        return {
            "items": [
                {
                    "id": order.id,
                    "state": order.state.value,
                    "reservation_ids": [
                        r.id for r in self.repo.get_reservations_for_order(order.id)
                    ],
                    "created_at": order.created_at,
                }
                for order in orders
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    def _format_reservation(reservation) -> dict:
        return {
            "id": reservation.id,
            "sku_code": reservation.sku_code,
            "quantity": reservation.quantity,
            "state": reservation.state.value,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
        }
