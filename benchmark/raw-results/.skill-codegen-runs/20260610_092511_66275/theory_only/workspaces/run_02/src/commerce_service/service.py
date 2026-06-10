import uuid
from datetime import datetime, timedelta

from .models import OrderModel, OrderStatus, ReservationModel, ReservationStatus
from .repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository
        self.reservation_ttl_minutes = 30

    def create_sku(self, sku_id: str, name: str, description: str | None = None):
        existing = self.repo.get_sku(sku_id)
        if existing:
            raise ValueError(f"SKU already exists: {sku_id}")
        sku = self.repo.create_sku(sku_id, name, description)
        self.repo.create_stock(sku_id)
        return sku

    def get_sku(self, sku_id: str):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU not found: {sku_id}")
        return sku

    def adjust_stock(self, sku_id: str, quantity_delta: int):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU not found: {sku_id}")
        stock = self.repo.update_stock(sku_id, quantity_delta)
        if stock.quantity_available < 0:
            raise ValueError(f"Stock cannot be negative for SKU: {sku_id}")
        return stock

    def create_reservation(self, sku_id: str, quantity: int, idempotency_key: str | None = None):
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU not found: {sku_id}")

        self.repo.reserve_stock(sku_id, quantity)

        reservation = ReservationModel(
            id=str(uuid.uuid4()),
            sku_id=sku_id,
            quantity=quantity,
            status=ReservationStatus.PENDING,
            expires_at=datetime.utcnow() + timedelta(minutes=self.reservation_ttl_minutes),
            idempotency_key=idempotency_key,
        )
        return self.repo.create_reservation(reservation)

    def get_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation.status == ReservationStatus.PENDING and datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            self.repo.release_stock(reservation.sku_id, reservation.quantity)
            reservation.status = ReservationStatus.EXPIRED

        return reservation

    def confirm_reservation(self, reservation_id: str, idempotency_key: str | None = None):
        if idempotency_key:
            order = self.repo.get_order_by_reservation_id(reservation_id)
            if order:
                return order

        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(
                f"Cannot confirm reservation with status {reservation.status}: {reservation_id}"
            )

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            self.repo.release_stock(reservation.sku_id, reservation.quantity)
            raise ValueError(f"Reservation has expired: {reservation_id}")

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

        order = OrderModel(
            id=str(uuid.uuid4()),
            reservation_id=reservation_id,
            status=OrderStatus.CONFIRMED,
        )
        return self.repo.create_order(order)

    def cancel_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation.status not in (ReservationStatus.PENDING, ReservationStatus.CONFIRMED):
            raise ValueError(
                f"Cannot cancel reservation with status {reservation.status}: {reservation_id}"
            )

        was_pending = reservation.status == ReservationStatus.PENDING
        updated_reservation = self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED
        )
        if was_pending:
            self.repo.release_stock(reservation.sku_id, reservation.quantity)

        return updated_reservation

    def get_order(self, order_id: str):
        order = self.repo.get_order(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")
        return order

    def list_orders(self, skip: int = 0, limit: int = 10):
        if skip < 0 or limit < 1:
            raise ValueError("Invalid pagination parameters")
        return self.repo.list_orders(skip, limit)
