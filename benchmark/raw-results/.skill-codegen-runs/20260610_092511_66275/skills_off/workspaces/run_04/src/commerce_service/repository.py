from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Order, Reservation, SKU


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # SKU operations

    def create_sku(self, product_id: str, name: str, initial_stock: int) -> SKU:
        sku = SKU(product_id=product_id, name=name, current_stock=initial_stock)
        self.session.add(sku)
        self.session.commit()
        return sku

    def get_sku(self, product_id: str) -> Optional[SKU]:
        return self.session.query(SKU).filter(SKU.product_id == product_id).first()

    def adjust_stock(self, product_id: str, delta: int) -> Optional[SKU]:
        sku = self.get_sku(product_id)
        if not sku:
            return None
        sku.current_stock += delta
        self.session.commit()
        return sku

    # Reservation operations

    def create_reservation(
        self, reservation_id: str, product_id: str, quantity: int, idempotency_key: str, expires_at: datetime
    ) -> Reservation:
        reservation = Reservation(
            id=reservation_id,
            product_id=product_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get_reservation(self, reservation_id: str) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(Reservation.idempotency_key == idempotency_key).first()

    def update_reservation_status(self, reservation_id: str, status: str) -> Optional[Reservation]:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.session.commit()
        return reservation

    # Order operations

    def create_order(self, order_id: str, reservation_id: str, product_id: str, quantity: int) -> Order:
        order = Order(id=order_id, reservation_id=reservation_id, product_id=product_id, quantity=quantity)
        self.session.add(order)
        self.session.commit()
        return order

    def get_order(self, order_id: str) -> Optional[Order]:
        return self.session.query(Order).filter(Order.id == order_id).first()

    def list_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[Order], int]:
        total = self.session.query(func.count(Order.id)).scalar()
        orders = self.session.query(Order).limit(limit).offset(offset).all()
        return orders, total

    def update_order_status(self, order_id: str, status: str) -> Optional[Order]:
        order = self.get_order(order_id)
        if not order:
            return None
        order.status = status
        order.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        return order
