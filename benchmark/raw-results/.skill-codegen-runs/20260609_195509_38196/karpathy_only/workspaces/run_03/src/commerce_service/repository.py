"""Data access layer."""

from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    Base,
    OrderModel,
    OrderStatus,
    ReservationModel,
    ReservationStatus,
    SKUModel,
    StockModel,
)


class Repository:
    """Database access layer."""

    def __init__(self, db_url: str = "sqlite:///./commerce.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def create_sku(self, session: Session, sku_id: str, name: str) -> SKUModel:
        sku = SKUModel(id=sku_id, name=name)
        session.add(sku)
        session.commit()
        session.refresh(sku)
        return sku

    def get_sku(self, session: Session, sku_id: str) -> Optional[SKUModel]:
        stmt = select(SKUModel).where(SKUModel.id == sku_id)
        return session.scalar(stmt)

    def get_or_create_stock(self, session: Session, sku_id: str) -> StockModel:
        stmt = select(StockModel).where(StockModel.sku_id == sku_id)
        stock = session.scalar(stmt)
        if stock is None:
            stock = StockModel(sku_id=sku_id, quantity=0)
            session.add(stock)
            session.commit()
            session.refresh(stock)
        return stock

    def update_stock(self, session: Session, sku_id: str, delta: int) -> StockModel:
        stock = self.get_or_create_stock(session, sku_id)
        stock.quantity = max(0, stock.quantity + delta)
        session.commit()
        session.refresh(stock)
        return stock

    def get_stock(self, session: Session, sku_id: str) -> Optional[StockModel]:
        stmt = select(StockModel).where(StockModel.sku_id == sku_id)
        return session.scalar(stmt)

    def create_reservation(
        self,
        session: Session,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> ReservationModel:
        reservation = ReservationModel(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        session.add(reservation)
        session.commit()
        session.refresh(reservation)
        return reservation

    def get_reservation(self, session: Session, reservation_id: str) -> Optional[ReservationModel]:
        stmt = select(ReservationModel).where(ReservationModel.id == reservation_id)
        return session.scalar(stmt)

    def get_reservation_by_idempotency_key(
        self, session: Session, idempotency_key: str
    ) -> Optional[ReservationModel]:
        stmt = select(ReservationModel).where(
            ReservationModel.idempotency_key == idempotency_key
        )
        return session.scalar(stmt)

    def update_reservation_status(
        self, session: Session, reservation_id: str, status: ReservationStatus
    ) -> ReservationModel:
        reservation = self.get_reservation(session, reservation_id)
        if reservation is None:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.status = status
        session.commit()
        session.refresh(reservation)
        return reservation

    def create_order(
        self,
        session: Session,
        order_id: str,
        reservation_id: str,
        sku_id: str,
        quantity: int,
    ) -> OrderModel:
        order = OrderModel(
            id=order_id,
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status=OrderStatus.RESERVED,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order

    def get_order(self, session: Session, order_id: str) -> Optional[OrderModel]:
        stmt = select(OrderModel).where(OrderModel.id == order_id)
        return session.scalar(stmt)

    def get_order_by_reservation_id(self, session: Session, reservation_id: str) -> Optional[OrderModel]:
        stmt = select(OrderModel).where(OrderModel.reservation_id == reservation_id)
        return session.scalar(stmt)

    def update_order_status(
        self, session: Session, order_id: str, status: OrderStatus
    ) -> OrderModel:
        order = self.get_order(session, order_id)
        if order is None:
            raise ValueError(f"Order {order_id} not found")
        order.status = status
        session.commit()
        session.refresh(order)
        return order

    def list_orders(
        self, session: Session, page: int = 1, page_size: int = 10
    ) -> tuple[list[OrderModel], int]:
        stmt = select(OrderModel)
        total = session.scalar(select(func.count(OrderModel.id)))

        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        items = session.scalars(stmt).all()

        return items, total

    def cleanup_expired_reservations(self, session: Session) -> int:
        """Mark expired reservations as expired. Returns count of updated rows."""
        now = datetime.utcnow()
        stmt = (
            select(ReservationModel)
            .where(ReservationModel.expires_at <= now)
            .where(ReservationModel.status == ReservationStatus.PENDING)
        )
        expired = session.scalars(stmt).all()
        for reservation in expired:
            reservation.status = ReservationStatus.EXPIRED
        session.commit()
        return len(expired)
