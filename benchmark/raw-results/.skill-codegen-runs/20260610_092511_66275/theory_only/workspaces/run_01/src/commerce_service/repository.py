"""Data access layer. Encapsulates all database operations."""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import IntegrityError

from .models import Base, SkuModel, StockModel, ReservationModel, OrderModel


class Database:
    def __init__(self, db_url: str = "sqlite:///./commerce.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()


class SkuRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, sku_id: str, name: str) -> SkuModel:
        sku = SkuModel(id=sku_id, name=name)
        self.session.add(sku)
        self.session.commit()
        self.session.refresh(sku)
        return sku

    def get(self, sku_id: str) -> Optional[SkuModel]:
        return self.session.query(SkuModel).filter(SkuModel.id == sku_id).first()


class StockRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create(self, sku_id: str) -> StockModel:
        stock = self.session.query(StockModel).filter(StockModel.sku_id == sku_id).first()
        if not stock:
            stock = StockModel(sku_id=sku_id, quantity=0, reserved=0)
            self.session.add(stock)
            self.session.commit()
            self.session.refresh(stock)
        return stock

    def adjust_quantity(self, sku_id: str, delta: int) -> StockModel:
        stock = self.get_or_create(sku_id)
        stock.quantity += delta
        stock.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(stock)
        return stock

    def reserve(self, sku_id: str, quantity: int) -> bool:
        stock = self.get_or_create(sku_id)
        available = stock.quantity - stock.reserved
        if available < quantity:
            return False
        stock.reserved += quantity
        stock.updated_at = datetime.utcnow()
        self.session.commit()
        return True

    def release_reservation(self, sku_id: str, quantity: int) -> StockModel:
        stock = self.get_or_create(sku_id)
        stock.reserved -= quantity
        stock.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(stock)
        return stock

    def confirm_reservation(self, sku_id: str, quantity: int) -> StockModel:
        stock = self.get_or_create(sku_id)
        stock.quantity -= quantity
        stock.reserved -= quantity
        stock.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(stock)
        return stock


class ReservationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        ttl_seconds: int,
        idempotency_key: Optional[str] = None,
    ) -> ReservationModel:
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        reservation = ReservationModel(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status="pending",
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )
        self.session.add(reservation)
        try:
            self.session.commit()
            self.session.refresh(reservation)
            return reservation
        except IntegrityError:
            self.session.rollback()
            return None

    def get(self, reservation_id: str) -> Optional[ReservationModel]:
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

    def update_status(self, reservation_id: str, status: str) -> ReservationModel:
        reservation = self.get(reservation_id)
        reservation.status = status
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_expired(self) -> list[ReservationModel]:
        return (
            self.session.query(ReservationModel)
            .filter(
                ReservationModel.status == "pending",
                ReservationModel.expires_at <= datetime.utcnow(),
            )
            .all()
        )


class OrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, order_id: str, sku_id: str, quantity: int) -> OrderModel:
        order = OrderModel(id=order_id, sku_id=sku_id, quantity=quantity, status="confirmed")
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get(self, order_id: str) -> Optional[OrderModel]:
        return self.session.query(OrderModel).filter(OrderModel.id == order_id).first()

    def list_orders(self, offset: int = 0, limit: int = 20) -> tuple[list[OrderModel], int]:
        total = self.session.query(OrderModel).count()
        orders = (
            self.session.query(OrderModel)
            .order_by(OrderModel.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return orders, total
