from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_
from commerce_service.models import (
    SKUModel,
    ReservationModel,
    OrderModel,
    OrderReservationModel,
    ReservationState,
    OrderState,
)


class Repository:
    def __init__(self, db: Session):
        self.db = db

    # SKU operations
    def create_sku(self, sku_id: str, code: str, name: str, initial_stock: int = 0) -> SKUModel:
        sku = SKUModel(id=sku_id, code=code, name=name, available_stock=initial_stock)
        self.db.add(sku)
        self.db.commit()
        return sku

    def get_sku_by_code(self, code: str) -> SKUModel | None:
        return self.db.query(SKUModel).filter(SKUModel.code == code).first()

    def adjust_stock(self, code: str, quantity: int) -> SKUModel:
        sku = self.get_sku_by_code(code)
        if not sku:
            raise ValueError(f"SKU {code} not found")
        sku.available_stock += quantity
        self.db.commit()
        return sku

    # Reservation operations
    def create_reservation(
        self,
        reservation_id: str,
        sku_code: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: str | None = None,
    ) -> ReservationModel:
        reservation = ReservationModel(
            id=reservation_id,
            sku_code=sku_code,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.db.add(reservation)
        self.db.commit()
        return reservation

    def get_reservation_by_id(self, reservation_id: str) -> ReservationModel | None:
        return self.db.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, key: str) -> ReservationModel | None:
        return self.db.query(ReservationModel).filter(ReservationModel.idempotency_key == key).first()

    def update_reservation_state(
        self, reservation_id: str, state: ReservationState
    ) -> ReservationModel:
        reservation = self.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.state = state
        self.db.commit()
        return reservation

    def get_pending_reservations_for_sku(self, sku_code: str) -> list[ReservationModel]:
        return self.db.query(ReservationModel).filter(
            and_(
                ReservationModel.sku_code == sku_code,
                ReservationModel.state == ReservationState.PENDING,
            )
        ).all()

    # Order operations
    def create_order(self, order_id: str, state: OrderState = OrderState.PENDING) -> OrderModel:
        order = OrderModel(id=order_id, state=state)
        self.db.add(order)
        self.db.commit()
        return order

    def get_order_by_id(self, order_id: str) -> OrderModel | None:
        return self.db.query(OrderModel).filter(OrderModel.id == order_id).first()

    def list_orders(self, offset: int = 0, limit: int = 10) -> tuple[list[OrderModel], int]:
        total = self.db.query(OrderModel).count()
        orders = self.db.query(OrderModel).offset(offset).limit(limit).all()
        return orders, total

    def update_order_state(self, order_id: str, state: OrderState) -> OrderModel:
        order = self.get_order_by_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        order.state = state
        self.db.commit()
        return order

    def add_reservation_to_order(self, order_id: str, reservation_id: str, link_id: str):
        link = OrderReservationModel(id=link_id, order_id=order_id, reservation_id=reservation_id)
        self.db.add(link)
        self.db.commit()

    def get_reservations_for_order(self, order_id: str) -> list[ReservationModel]:
        links = self.db.query(OrderReservationModel).filter(
            OrderReservationModel.order_id == order_id
        ).all()
        reservation_ids = [link.reservation_id for link in links]
        if not reservation_ids:
            return []
        return self.db.query(ReservationModel).filter(
            ReservationModel.id.in_(reservation_ids)
        ).all()
