"""Data access layer."""

from datetime import datetime

from sqlalchemy.orm import Session

from .models import OrderModel, ReservationModel, SKUModel


class Repository:
    """Data access for SKUs, reservations, and orders."""

    def __init__(self, session: Session):
        self.session = session

    # SKU operations

    def create_sku(self, sku_code: str, stock_available: int) -> SKUModel:
        sku = SKUModel(sku_code=sku_code, stock_available=stock_available)
        self.session.add(sku)
        self.session.commit()
        self.session.refresh(sku)
        return sku

    def get_sku_by_id(self, sku_id: int) -> SKUModel | None:
        return self.session.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def get_sku_by_code(self, sku_code: str) -> SKUModel | None:
        return self.session.query(SKUModel).filter(SKUModel.sku_code == sku_code).first()

    def adjust_stock(self, sku_id: int, delta: int) -> SKUModel | None:
        sku = self.get_sku_by_id(sku_id)
        if not sku:
            return None
        sku.stock_available += delta
        self.session.commit()
        self.session.refresh(sku)
        return sku

    # Reservation operations

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_reservation_by_id(self, reservation_id: int) -> ReservationModel | None:
        return self.session.query(ReservationModel).filter(
            ReservationModel.id == reservation_id
        ).first()

    def get_reservation_by_idempotency_key(self, key: str) -> ReservationModel | None:
        return self.session.query(ReservationModel).filter(
            ReservationModel.idempotency_key == key
        ).first()

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> ReservationModel | None:
        reservation = self.get_reservation_by_id(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    # Order operations

    def create_order(self, reservation_id: int) -> OrderModel:
        order = OrderModel(reservation_id=reservation_id)
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_order_by_id(self, order_id: int) -> OrderModel | None:
        return self.session.query(OrderModel).filter(OrderModel.id == order_id).first()

    def list_orders(self, offset: int = 0, limit: int = 20) -> tuple[list[OrderModel], int]:
        query = self.session.query(OrderModel)
        total = query.count()
        orders = query.offset(offset).limit(limit).all()
        return orders, total

    def update_order_status(self, order_id: int, status: str) -> OrderModel | None:
        order = self.get_order_by_id(order_id)
        if not order:
            return None
        order.status = status
        self.session.commit()
        self.session.refresh(order)
        return order
