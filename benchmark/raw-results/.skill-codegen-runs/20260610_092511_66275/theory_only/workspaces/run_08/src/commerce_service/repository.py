from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from .models import Base, SKUModel, InventoryModel, ReservationModel, OrderModel

DATABASE_URL = "sqlite:///./commerce.db"


def get_engine():
    return create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def get_session_factory(engine=None):
    if engine is None:
        engine = get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(engine=None):
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(bind=engine)


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku_id: str, name: str) -> SKUModel:
        sku = SKUModel(id=sku_id, name=name)
        self.session.add(sku)
        self.session.commit()
        self.session.refresh(sku)
        return sku

    def get_sku(self, sku_id: str) -> SKUModel | None:
        return self.session.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def get_or_create_inventory(self, sku_id: str) -> InventoryModel:
        inv = self.session.query(InventoryModel).filter(InventoryModel.sku_id == sku_id).first()
        if inv is None:
            inv = InventoryModel(sku_id=sku_id, quantity=0, reserved=0)
            self.session.add(inv)
            self.session.commit()
            self.session.refresh(inv)
        return inv

    def adjust_stock(self, sku_id: str, delta: int) -> InventoryModel:
        inv = self.get_or_create_inventory(sku_id)
        inv.quantity += delta
        self.session.commit()
        self.session.refresh(inv)
        return inv

    def get_inventory(self, sku_id: str) -> InventoryModel | None:
        return self.session.query(InventoryModel).filter(InventoryModel.sku_id == sku_id).first()

    def create_reservation(
        self, reservation_id: str, sku_id: str, quantity: int, idempotency_key: str | None
    ) -> ReservationModel:
        res = ReservationModel(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status="pending",
            idempotency_key=idempotency_key,
        )
        self.session.add(res)
        self.session.commit()
        self.session.refresh(res)
        return res

    def get_reservation(self, reservation_id: str) -> ReservationModel | None:
        return self.session.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> ReservationModel | None:
        return self.session.query(ReservationModel).filter(
            ReservationModel.idempotency_key == idempotency_key
        ).first()

    def update_reservation_status(self, reservation_id: str, status: str) -> ReservationModel:
        res = self.get_reservation(reservation_id)
        if res is None:
            raise ValueError(f"Reservation {reservation_id} not found")
        res.status = status
        if status == "confirmed":
            from datetime import datetime
            res.confirmed_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(res)
        return res

    def reserve_stock(self, sku_id: str, quantity: int) -> InventoryModel:
        inv = self.get_inventory(sku_id)
        if inv is None:
            raise ValueError(f"Inventory for SKU {sku_id} not found")
        inv.reserved += quantity
        self.session.commit()
        self.session.refresh(inv)
        return inv

    def release_reserved_stock(self, sku_id: str, quantity: int) -> InventoryModel:
        inv = self.get_inventory(sku_id)
        if inv is None:
            raise ValueError(f"Inventory for SKU {sku_id} not found")
        inv.reserved = max(0, inv.reserved - quantity)
        self.session.commit()
        self.session.refresh(inv)
        return inv

    def create_order(
        self, order_id: str, reservation_id: str, sku_id: str, quantity: int, status: str
    ) -> OrderModel:
        order = OrderModel(
            id=order_id,
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status=status,
        )
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_order(self, order_id: str) -> OrderModel | None:
        return self.session.query(OrderModel).filter(OrderModel.id == order_id).first()

    def update_order_status(self, order_id: str, status: str) -> OrderModel:
        order = self.get_order(order_id)
        if order is None:
            raise ValueError(f"Order {order_id} not found")
        order.status = status
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> tuple[list[OrderModel], int]:
        query = self.session.query(OrderModel)
        total = query.count()
        offset = (page - 1) * size
        items = query.offset(offset).limit(size).all()
        return items, total
