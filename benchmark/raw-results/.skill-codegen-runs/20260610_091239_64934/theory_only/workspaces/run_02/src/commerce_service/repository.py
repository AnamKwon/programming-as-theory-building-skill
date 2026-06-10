from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import Order, OrderStatus, Reservation, ReservationStatus, SKU


class SKURepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, sku_id: str) -> Optional[SKU]:
        return self.session.query(SKU).filter(SKU.id == sku_id).first()

    def create(self, sku_id: str, name: str, initial_stock: int = 0) -> SKU:
        sku = SKU(id=sku_id, name=name, available_stock=initial_stock, reserved_stock=0)
        self.session.add(sku)
        self.session.commit()
        return sku

    def update_stock(self, sku_id: str, available_delta: int, reserved_delta: int = 0) -> SKU:
        sku = self.get_by_id(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        sku.available_stock += available_delta
        sku.reserved_stock += reserved_delta
        self.session.commit()
        return sku


class ReservationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, reservation_id: str) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(Reservation.id == reservation_id).first()

    def create(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at: datetime,
    ) -> Reservation:
        reservation = Reservation(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status=ReservationStatus.ACTIVE,
            expires_at=expires_at,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get_by_sku(self, sku_id: str) -> list[Reservation]:
        return (
            self.session.query(Reservation)
            .filter(Reservation.sku_id == sku_id, Reservation.status == ReservationStatus.ACTIVE)
            .all()
        )

    def update_status(self, reservation_id: str, status: ReservationStatus) -> Reservation:
        reservation = self.get_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        if status == ReservationStatus.CONFIRMED:
            reservation.confirmed_at = datetime.utcnow()
        reservation.status = status
        self.session.commit()
        return reservation

    def get_expired(self) -> list[Reservation]:
        return (
            self.session.query(Reservation)
            .filter(
                Reservation.status == ReservationStatus.ACTIVE,
                Reservation.expires_at <= datetime.utcnow(),
            )
            .all()
        )

    def get_by_idempotency_key(self, key: str) -> Optional[Reservation]:
        return (
            self.session.query(Reservation)
            .filter(Reservation.idempotency_key == key)
            .first()
        )


class OrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, order_id: str) -> Optional[Order]:
        return self.session.query(Order).filter(Order.id == order_id).first()

    def get_by_idempotency_key(self, key: str) -> Optional[Order]:
        return (
            self.session.query(Order)
            .filter(Order.idempotency_key == key, Order.status != OrderStatus.CANCELLED)
            .first()
        )

    def create(
        self,
        order_id: str,
        sku_id: str,
        quantity: int,
        reservation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Order:
        order = Order(
            id=order_id,
            sku_id=sku_id,
            quantity=quantity,
            status=OrderStatus.PENDING,
            reservation_id=reservation_id,
            idempotency_key=idempotency_key,
        )
        self.session.add(order)
        self.session.commit()
        return order

    def update_status(self, order_id: str, status: OrderStatus) -> Order:
        order = self.get_by_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        if status == OrderStatus.CONFIRMED:
            order.confirmed_at = datetime.utcnow()
        order.status = status
        self.session.commit()
        return order

    def list_orders(self, offset: int = 0, limit: int = 10) -> tuple[list[Order], int]:
        total = self.session.query(Order).count()
        orders = (
            self.session.query(Order)
            .order_by(Order.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return orders, total
