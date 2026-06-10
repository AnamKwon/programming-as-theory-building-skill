from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from commerce_service.repository import Repository
from commerce_service.models import SKU, Stock, Reservation, Order


class ReservationError(Exception):
    pass


class InsufficientStockError(ReservationError):
    pass


class ReservationExpiredError(ReservationError):
    pass


class ReservationNotFoundError(ReservationError):
    pass


class OrderService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, session: Session, code: str, name: str) -> SKU:
        existing = self.repo.get_sku_by_code(session, code)
        if existing:
            return existing
        return self.repo.create_sku(session, code, name)

    def adjust_stock(self, session: Session, sku_id: str, quantity: int) -> Stock:
        sku = self.repo.get_sku_by_id(session, sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return self.repo.adjust_stock(session, sku_id, quantity)

    def get_stock(self, session: Session, sku_id: str) -> Stock:
        sku = self.repo.get_sku_by_id(session, sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return self.repo.get_stock(session, sku_id)

    def create_reservation(
        self, session: Session, sku_id: str, quantity: int, idempotency_key: str
    ) -> Reservation:
        existing = self.repo.get_reservation_by_idempotency_key(session, idempotency_key)
        if existing:
            if existing.is_expired():
                raise ReservationExpiredError("Reservation has expired")
            return existing

        sku = self.repo.get_sku_by_id(session, sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        stock = self.repo.get_stock(session, sku_id)
        available = stock.quantity - stock.reserved
        if available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock: available={available}, requested={quantity}"
            )

        try:
            reservation = self.repo.create_reservation(session, sku_id, quantity, idempotency_key)
            self.repo.reserve_stock(session, sku_id, quantity)
            return reservation
        except IntegrityError:
            session.rollback()
            existing = self.repo.get_reservation_by_idempotency_key(session, idempotency_key)
            if existing.is_expired():
                raise ReservationExpiredError("Reservation has expired")
            return existing

    def confirm_reservation(self, session: Session, reservation_id: str) -> Order:
        reservation = self.repo.get_reservation_by_id(session, reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.is_expired():
            self.repo.unreserve_stock(session, reservation.sku_id, reservation.quantity)
            session.delete(reservation)
            session.commit()
            raise ReservationExpiredError("Reservation has expired")

        if reservation.is_confirmed():
            order = self.repo.get_orders_by_reservation_id(session, reservation_id)
            if order:
                return order
            raise ReservationError("Reservation already confirmed but no order found")

        self.repo.confirm_reservation(session, reservation_id)
        order = self.repo.create_order(session, reservation_id)
        return order

    def cancel_reservation(self, session: Session, reservation_id: str) -> None:
        reservation = self.repo.get_reservation_by_id(session, reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.is_confirmed():
            order = self.repo.get_orders_by_reservation_id(session, reservation_id)
            if order and order.status == "PENDING":
                self.repo.update_order_status(session, order.id, "CANCELLED")

        self.repo.cancel_reservation(session, reservation_id)

    def get_order(self, session: Session, order_id: str) -> Order:
        order = self.repo.get_order_by_id(session, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return order

    def list_orders(self, session: Session, limit: int = 20, offset: int = 0) -> tuple:
        return self.repo.list_orders(session, limit, offset)
