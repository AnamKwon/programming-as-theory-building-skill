import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import models
from .repository import OrderRepository, ReservationRepository, SKURepository, StockRepository


class CommerceService:
    RESERVATION_EXPIRY_MINUTES = 10

    def __init__(self, db: Session):
        self.db = db
        self.skus = SKURepository(db)
        self.stock = StockRepository(db)
        self.reservations = ReservationRepository(db)
        self.orders = OrderRepository(db)

    def create_sku(self, sku_id: str, name: str, price: float) -> models.SKU:
        existing = self.skus.get(sku_id)
        if existing:
            raise ValueError(f"SKU {sku_id} already exists")
        return self.skus.create(sku_id, name, price)

    def adjust_stock(self, sku_id: str, quantity: int) -> models.Stock:
        sku = self.skus.get(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return self.stock.adjust(sku_id, quantity)

    def create_reservation(
        self,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
    ) -> models.Reservation:
        existing = self.reservations.get_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku = self.skus.get(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        stock = self.stock.get_or_create(sku_id)
        if stock.quantity < quantity:
            raise ValueError(
                f"Insufficient stock for {sku_id}: requested {quantity}, available {stock.quantity}"
            )

        order_id = str(uuid.uuid4())
        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_EXPIRY_MINUTES)

        reservation = self.reservations.create(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            order_id=order_id,
        )

        order = self.orders.create(order_id)

        stock.quantity -= quantity
        self.db.commit()

        return reservation

    def confirm_reservation(self, reservation_id: str) -> models.Reservation:
        reservation = self.reservations.get(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status == models.ReservationStatus.CONFIRMED:
            return reservation

        if reservation.status == models.ReservationStatus.CANCELLED:
            raise ValueError(f"Reservation {reservation_id} is cancelled")

        if datetime.utcnow() > reservation.expires_at:
            self.reservations.update_status(reservation_id, models.ReservationStatus.EXPIRED)
            raise ValueError(f"Reservation {reservation_id} has expired")

        self.reservations.update_status(reservation_id, models.ReservationStatus.CONFIRMED)
        order = self.orders.update_status(reservation.order_id, models.OrderStatus.CONFIRMED)

        return self.reservations.get(reservation_id)

    def cancel_reservation(self, reservation_id: str) -> models.Reservation:
        reservation = self.reservations.get(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status == models.ReservationStatus.CANCELLED:
            return reservation

        if reservation.status == models.ReservationStatus.CONFIRMED:
            raise ValueError(f"Cannot cancel confirmed reservation {reservation_id}")

        self.reservations.update_status(reservation_id, models.ReservationStatus.CANCELLED)

        stock = self.stock.get_or_create(reservation.sku_id)
        stock.quantity += reservation.quantity
        self.db.commit()

        if reservation.status == models.ReservationStatus.PENDING:
            order = self.orders.update_status(reservation.order_id, models.OrderStatus.CANCELLED)

        return self.reservations.get(reservation_id)

    def get_order(self, order_id: str) -> models.Order:
        order = self.orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return order

    def list_orders(self, limit: int, offset: int) -> tuple[list[models.Order], int]:
        return self.orders.list(limit, offset)
