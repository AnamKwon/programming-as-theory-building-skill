from datetime import datetime
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .models import Order, OrderItem, Reservation, ReservationState, SKU


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # SKU operations
    def create_sku(self, sku_id: str, name: str, quantity: int) -> SKU:
        sku = SKU(id=sku_id, name=name, available_stock=quantity)
        self.session.add(sku)
        self.session.commit()
        return sku

    def get_sku(self, sku_id: str) -> Optional[SKU]:
        return self.session.query(SKU).filter(SKU.id == sku_id).first()

    def adjust_stock(self, sku_id: str, quantity: int) -> Optional[SKU]:
        sku = self.get_sku(sku_id)
        if not sku:
            return None
        sku.available_stock += quantity
        self.session.commit()
        return sku

    # Reservation operations
    def create_reservation(
        self, res_id: str, sku_id: str, quantity: int, expires_at: datetime, idempotency_key: str
    ) -> Reservation:
        reservation = Reservation(
            id=res_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get_reservation(self, res_id: str) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(Reservation.id == res_id).first()

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(Reservation.idempotency_key == key).first()

    def update_reservation_state(self, res_id: str, state: ReservationState) -> Optional[Reservation]:
        reservation = self.get_reservation(res_id)
        if reservation:
            reservation.state = state
            self.session.commit()
        return reservation

    def list_expired_reservations(self, now: datetime) -> list[Reservation]:
        return (
            self.session.query(Reservation)
            .filter(
                and_(
                    Reservation.expires_at <= now,
                    Reservation.state == ReservationState.PENDING,
                )
            )
            .all()
        )

    # Order operations
    def create_order(self, order_id: str) -> Order:
        order = Order(id=order_id)
        self.session.add(order)
        self.session.commit()
        return order

    def get_order(self, order_id: str) -> Optional[Order]:
        return self.session.query(Order).filter(Order.id == order_id).first()

    def add_item_to_order(self, order_id: str, reservation_id: str) -> OrderItem:
        order_item = OrderItem(id=f"{order_id}-{reservation_id}", order_id=order_id, reservation_id=reservation_id)
        self.session.add(order_item)
        self.session.commit()
        return order_item

    def list_orders(self, page: int = 1, size: int = 20) -> tuple[list[Order], int]:
        total = self.session.query(Order).count()
        offset = (page - 1) * size
        orders = self.session.query(Order).offset(offset).limit(size).all()
        return orders, total

    def update_order_state(self, order_id: str, state) -> Optional[Order]:
        order = self.get_order(order_id)
        if order:
            order.state = state
            order.updated_at = datetime.utcnow()
            self.session.commit()
        return order
