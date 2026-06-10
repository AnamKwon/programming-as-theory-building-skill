from datetime import datetime, UTC
from .repository import Repository, ReservationStatus, OrderStatus, ReservationModel, OrderModel


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class IdempotencyConflictError(Exception):
    pass


class Service:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, name: str, quantity: int) -> dict:
        existing = self.repo.get_sku_by_name(name)
        if existing:
            raise ValueError(f"SKU '{name}' already exists")
        sku = self.repo.create_sku(name, quantity)
        return {
            "id": sku.id,
            "name": sku.name,
            "quantity": sku.quantity,
            "created_at": sku.created_at,
        }

    def get_sku(self, sku_id: int) -> dict:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return {
            "id": sku.id,
            "name": sku.name,
            "quantity": sku.quantity,
            "created_at": sku.created_at,
        }

    def adjust_stock(self, sku_id: int, delta: int) -> dict:
        sku = self.repo.adjust_stock(sku_id, delta)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return {
            "id": sku.id,
            "name": sku.name,
            "quantity": sku.quantity,
            "created_at": sku.created_at,
        }

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str
    ) -> dict:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == ReservationStatus.PENDING:
                return self._reservation_to_dict(existing)
            else:
                raise IdempotencyConflictError(
                    f"Reservation with idempotency key already exists with status {existing.status}"
                )

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        if sku.quantity < quantity:
            raise InsufficientStockError(
                f"Insufficient stock: requested {quantity}, available {sku.quantity}"
            )

        reservation = self.repo.create_reservation(sku_id, quantity, idempotency_key)
        return self._reservation_to_dict(reservation)

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if self._is_reservation_expired(reservation):
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.status != ReservationStatus.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation with status {reservation.status}"
            )

        updated = self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED
        )
        return self._reservation_to_dict(updated)

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status in (ReservationStatus.CANCELLED, ReservationStatus.EXPIRED):
            raise InvalidStateTransitionError(
                f"Cannot cancel reservation with status {reservation.status}"
            )

        updated = self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED
        )
        return self._reservation_to_dict(updated)

    def get_orders(self, offset: int = 0, limit: int = 10) -> dict:
        orders, total = self.repo.list_orders(offset, limit)
        return {
            "orders": [self._order_to_dict(order) for order in orders],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    def _is_reservation_expired(self, reservation: ReservationModel) -> bool:
        now = datetime.now(UTC)
        return now > reservation.expires_at

    def _reservation_to_dict(self, reservation: ReservationModel) -> dict:
        status = reservation.status.value
        if status == ReservationStatus.PENDING.value and self._is_reservation_expired(reservation):
            status = ReservationStatus.EXPIRED.value
        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": status,
            "idempotency_key": reservation.idempotency_key,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
        }

    def _order_to_dict(self, order: OrderModel) -> dict:
        reservations = self.repo.list_reservations_by_order(order.id)
        items = [
            {
                "reservation_id": res.id,
                "sku_id": res.sku_id,
                "quantity": res.quantity,
                "status": res.status.value,
            }
            for res in reservations
        ]
        return {
            "id": order.id,
            "status": order.status.value,
            "items": items,
            "total_quantity": sum(res.quantity for res in reservations),
            "created_at": order.created_at,
        }
