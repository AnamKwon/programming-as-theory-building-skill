from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from .models import SKUModel, ReservationModel, OrderModel, ReservationState


class Repository:
    def __init__(self, db: Session):
        self.db = db

    # SKU operations
    def create_sku(self, sku_id: str, stock_available: int) -> SKUModel:
        sku = SKUModel(sku_id=sku_id, stock_available=stock_available)
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def get_sku(self, sku_id: str) -> SKUModel | None:
        return self.db.query(SKUModel).filter(SKUModel.sku_id == sku_id).first()

    def update_sku_stock(self, sku_id: str, quantity_delta: int) -> SKUModel | None:
        sku = self.get_sku(sku_id)
        if sku is None:
            return None
        sku.stock_available += quantity_delta
        self.db.commit()
        self.db.refresh(sku)
        return sku

    # Reservation operations
    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: str | None = None,
    ) -> ReservationModel:
        reservation = ReservationModel(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
            state=ReservationState.PENDING,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: str) -> ReservationModel | None:
        return self.db.query(ReservationModel).filter(
            ReservationModel.reservation_id == reservation_id
        ).first()

    def get_reservation_by_idempotency_key(self, key: str) -> ReservationModel | None:
        return self.db.query(ReservationModel).filter(
            ReservationModel.idempotency_key == key
        ).first()

    def update_reservation_state(
        self, reservation_id: str, state: ReservationState
    ) -> ReservationModel | None:
        reservation = self.get_reservation(reservation_id)
        if reservation is None:
            return None
        reservation.state = state
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def list_expired_reservations(self, now: datetime) -> list[ReservationModel]:
        return self.db.query(ReservationModel).filter(
            ReservationModel.state == ReservationState.PENDING,
            ReservationModel.expires_at <= now,
        ).all()

    # Order operations
    def create_order(
        self,
        order_id: str,
        reservation_id: str,
        sku_id: str,
        quantity: int,
    ) -> OrderModel:
        order = OrderModel(
            order_id=order_id,
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            state=ReservationState.CONFIRMED,
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_order(self, order_id: str) -> OrderModel | None:
        return self.db.query(OrderModel).filter(
            OrderModel.order_id == order_id
        ).first()

    def list_orders(self, skip: int = 0, limit: int = 10) -> tuple[list[OrderModel], int]:
        total = self.db.query(func.count(OrderModel.order_id)).scalar()
        orders = self.db.query(OrderModel).offset(skip).limit(limit).all()
        return orders, total
