from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Order, Reservation, ReservationStatus, SKU, Stock


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # SKU operations
    def create_sku(self, code: str) -> SKU:
        sku = SKU(code=code)
        self.session.add(sku)
        self.session.flush()
        return sku

    def get_sku_by_code(self, code: str) -> SKU | None:
        stmt = select(SKU).where(SKU.code == code)
        return self.session.scalars(stmt).first()

    def get_sku_by_id(self, sku_id: int) -> SKU | None:
        return self.session.get(SKU, sku_id)

    # Stock operations
    def get_stock_by_sku_id(self, sku_id: int) -> Stock | None:
        stmt = select(Stock).where(Stock.sku_id == sku_id)
        return self.session.scalars(stmt).first()

    def create_stock(self, sku_id: int, quantity: int) -> Stock:
        stock = Stock(sku_id=sku_id, quantity=quantity)
        self.session.add(stock)
        self.session.flush()
        return stock

    def update_stock(self, sku_id: int, delta: int) -> Stock:
        stock = self.get_stock_by_sku_id(sku_id)
        if stock is None:
            stock = self.create_stock(sku_id, max(0, delta))
        else:
            stock.quantity = max(0, stock.quantity + delta)
        self.session.flush()
        return stock

    # Reservation operations
    def create_reservation(
        self, idempotency_key: str, sku_id: int, quantity: int, expires_at: datetime
    ) -> Reservation:
        reservation = Reservation(
            idempotency_key=idempotency_key,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
        )
        self.session.add(reservation)
        self.session.flush()
        return reservation

    def get_reservation_by_id(self, reservation_id: int) -> Reservation | None:
        return self.session.get(Reservation, reservation_id)

    def get_reservation_by_idempotency_key(self, key: str) -> Reservation | None:
        stmt = select(Reservation).where(Reservation.idempotency_key == key)
        return self.session.scalars(stmt).first()

    def update_reservation_status(
        self, reservation_id: int, status: ReservationStatus, order_id: int | None = None
    ) -> Reservation:
        reservation = self.get_reservation_by_id(reservation_id)
        if reservation:
            reservation.status = status
            if order_id is not None:
                reservation.order_id = order_id
            self.session.flush()
        return reservation

    def get_reserved_quantity(self, sku_id: int) -> int:
        stmt = select(Reservation).where(
            (Reservation.sku_id == sku_id)
            & (Reservation.status == ReservationStatus.PENDING)
            & (Reservation.expires_at > datetime.utcnow())
        )
        reservations = self.session.scalars(stmt).all()
        return sum(r.quantity for r in reservations)

    # Order operations
    def create_order(self, sku_id: int, quantity: int) -> Order:
        order = Order(sku_id=sku_id, quantity=quantity)
        self.session.add(order)
        self.session.flush()
        return order

    def get_order_by_id(self, order_id: int) -> Order | None:
        return self.session.get(Order, order_id)

    def list_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[Order], int]:
        stmt_count = select(Order)
        total = len(self.session.scalars(stmt_count).all())

        stmt = select(Order).limit(limit).offset(offset)
        orders = self.session.scalars(stmt).all()
        return orders, total

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
