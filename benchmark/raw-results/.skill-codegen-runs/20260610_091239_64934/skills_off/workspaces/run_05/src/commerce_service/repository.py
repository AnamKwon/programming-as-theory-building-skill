from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import OrderModel, ReservationModel, ReservationStatus, SKUModel


class SKURepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_code(self, sku_code: str) -> Optional[SKUModel]:
        return self.session.query(SKUModel).filter(SKUModel.sku == sku_code).first()

    def create(self, sku_code: str, name: str, stock: int) -> SKUModel:
        sku = SKUModel(sku=sku_code, name=name, stock=stock)
        self.session.add(sku)
        self.session.commit()
        self.session.refresh(sku)
        return sku

    def adjust_stock(self, sku_code: str, delta: int) -> SKUModel:
        sku = self.get_by_code(sku_code)
        if not sku:
            raise ValueError(f"SKU not found: {sku_code}")
        sku.stock += delta
        self.session.commit()
        self.session.refresh(sku)
        return sku


class ReservationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, reservation_id: int) -> Optional[ReservationModel]:
        return (
            self.session.query(ReservationModel)
            .filter(ReservationModel.id == reservation_id)
            .first()
        )

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationModel]:
        return (
            self.session.query(ReservationModel)
            .filter(ReservationModel.idempotency_key == idempotency_key)
            .first()
        )

    def create(
        self,
        sku_id: int,
        sku_code: str,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku_id=sku_id,
            sku_code=sku_code,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            status=ReservationStatus.PENDING,
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def update_status(self, reservation_id: int, status: str) -> ReservationModel:
        reservation = self.get_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {reservation_id}")
        reservation.status = status
        if status == ReservationStatus.CONFIRMED:
            reservation.confirmed_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(reservation)
        return reservation


class OrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self, reservation_id: int, sku: str, quantity: int, status: str
    ) -> OrderModel:
        order = OrderModel(
            reservation_id=reservation_id,
            sku=sku,
            quantity=quantity,
            status=status,
        )
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def list_orders(self, offset: int = 0, limit: int = 50) -> tuple[list[OrderModel], int]:
        query = self.session.query(OrderModel)
        total = query.count()
        orders = query.offset(offset).limit(limit).all()
        return orders, total

    def update_status(self, order_id: int, status: str) -> OrderModel:
        order = self.session.query(OrderModel).filter(OrderModel.id == order_id).first()
        if not order:
            raise ValueError(f"Order not found: {order_id}")
        order.status = status
        self.session.commit()
        self.session.refresh(order)
        return order
