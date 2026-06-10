from datetime import datetime

from commerce_service.models import ReservationStatus
from commerce_service.repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ReservationAlreadyProcessedError(Exception):
    pass


class Service:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, name: str, initial_stock: int) -> bool:
        return self.repo.create_sku(sku, name, initial_stock)

    def adjust_stock(self, sku: str, quantity: int) -> None:
        if not self.repo.adjust_stock(sku, quantity):
            raise ValueError(f"SKU {sku} not found")

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing["status"] == ReservationStatus.PENDING.value:
                return {
                    "reservation_id": existing["id"],
                    "sku": existing["sku"],
                    "quantity": existing["quantity"],
                    "status": ReservationStatus.PENDING,
                    "expires_at": existing["expires_at"],
                }
            else:
                raise ReservationAlreadyProcessedError(
                    f"Reservation already processed with status {existing['status']}"
                )

        sku_data = self.repo.get_sku(sku)
        if not sku_data:
            raise ValueError(f"SKU {sku} not found")

        if sku_data["available_stock"] < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku}: need {quantity}, have {sku_data['available_stock']}"
            )

        if not self.repo.reserve_stock(sku, quantity):
            raise InsufficientStockError(
                f"Insufficient stock for {sku}: race condition detected"
            )

        reservation_id = self.repo.create_reservation(sku, quantity, idempotency_key)
        if not reservation_id:
            self.repo.release_reserved_stock(sku, quantity)
            raise ValueError("Failed to create reservation")

        reservation = self.repo.get_reservation(reservation_id)
        return {
            "reservation_id": reservation["id"],
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": ReservationStatus(reservation["status"]),
            "expires_at": reservation["expires_at"],
        }

    def confirm_reservation(self, reservation_id: str) -> dict:
        self.repo.clean_expired_reservations()

        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation["status"] == ReservationStatus.EXPIRED.value:
            raise ReservationExpiredError(
                f"Reservation {reservation_id} has expired"
            )

        if reservation["status"] == ReservationStatus.CONFIRMED.value:
            if reservation["order_id"]:
                order = self.repo.get_order(reservation["order_id"])
                if order:
                    return {
                        "order_id": order["id"],
                        "sku": order["sku"],
                        "quantity": order["quantity"],
                        "status": order["status"],
                        "created_at": order["created_at"],
                        "updated_at": order["updated_at"],
                    }

        if reservation["status"] != ReservationStatus.PENDING.value:
            raise ValueError(
                f"Cannot confirm reservation in status {reservation['status']}"
            )

        expires_at = datetime.fromisoformat(reservation["expires_at"])
        if datetime.utcnow() > expires_at:
            self.repo.update_reservation_status(
                reservation_id, ReservationStatus.EXPIRED
            )
            self.repo.release_reserved_stock(
                reservation["sku"], reservation["quantity"]
            )
            raise ReservationExpiredError(
                f"Reservation {reservation_id} has expired"
            )

        order_id = self.repo.create_order(reservation["sku"], reservation["quantity"])

        self.repo.confirm_reservation_stock(
            reservation["sku"], reservation["quantity"]
        )

        self.repo.set_reservation_order(reservation_id, order_id)
        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED
        )

        order = self.repo.get_order(order_id)
        return {
            "order_id": order["id"],
            "sku": order["sku"],
            "quantity": order["quantity"],
            "status": order["status"],
            "created_at": order["created_at"],
            "updated_at": order["updated_at"],
        }

    def cancel_reservation(self, reservation_id: str) -> None:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation["status"] == ReservationStatus.PENDING.value:
            self.repo.release_reserved_stock(
                reservation["sku"], reservation["quantity"]
            )
            self.repo.update_reservation_status(
                reservation_id, ReservationStatus.CANCELLED
            )
        elif reservation["status"] != ReservationStatus.CANCELLED.value:
            raise ValueError(
                f"Cannot cancel reservation in status {reservation['status']}"
            )
