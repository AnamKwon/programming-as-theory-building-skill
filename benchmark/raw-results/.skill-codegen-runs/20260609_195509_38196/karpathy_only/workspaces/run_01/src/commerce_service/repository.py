"""Data access layer."""

from datetime import datetime
from sqlalchemy.orm import Session

from .models import SKUModel, ReservationModel, OrderModel


class SKURepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, name: str, quantity_available: float) -> SKUModel:
        sku = SKUModel(name=name, quantity_available=quantity_available)
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def get_by_id(self, sku_id: int) -> SKUModel | None:
        return self.db.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def update_quantity(self, sku_id: int, delta: float) -> SKUModel | None:
        sku = self.get_by_id(sku_id)
        if sku:
            sku.quantity_available += delta
            self.db.commit()
            self.db.refresh(sku)
        return sku


class ReservationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self, sku_id: int, quantity: float, idempotency_key: str, expires_at: datetime
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_by_id(self, reservation_id: int) -> ReservationModel | None:
        return self.db.query(ReservationModel).filter(
            ReservationModel.id == reservation_id
        ).first()

    def get_by_idempotency_key(self, idempotency_key: str) -> ReservationModel | None:
        return self.db.query(ReservationModel).filter(
            ReservationModel.idempotency_key == idempotency_key
        ).first()

    def update_status(self, reservation_id: int, status: str) -> ReservationModel | None:
        reservation = self.get_by_id(reservation_id)
        if reservation:
            reservation.status = status
            self.db.commit()
            self.db.refresh(reservation)
        return reservation

    def get_active_by_sku(self, sku_id: int) -> list[ReservationModel]:
        return self.db.query(ReservationModel).filter(
            ReservationModel.sku_id == sku_id,
            ReservationModel.status == "pending",
            ReservationModel.expires_at > datetime.utcnow(),
        ).all()


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, sku_id: int, quantity: float, status: str = "reserved") -> OrderModel:
        order = OrderModel(sku_id=sku_id, quantity=quantity, status=status)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_by_id(self, order_id: int) -> OrderModel | None:
        return self.db.query(OrderModel).filter(OrderModel.id == order_id).first()

    def list_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[OrderModel], int]:
        total = self.db.query(OrderModel).count()
        orders = self.db.query(OrderModel).offset(offset).limit(limit).all()
        return orders, total

    def update_status(self, order_id: int, status: str) -> OrderModel | None:
        order = self.get_by_id(order_id)
        if order:
            order.status = status
            self.db.commit()
            self.db.refresh(order)
        return order
