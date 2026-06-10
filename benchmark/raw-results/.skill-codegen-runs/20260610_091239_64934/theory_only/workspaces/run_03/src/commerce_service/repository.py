from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base, Order, Reservation, SKU, Stock


class Repository:
    def __init__(self, db_path: str = "sqlite:///commerce.db"):
        if db_path == "sqlite:///:memory:":
            self.engine = create_engine(
                db_path,
                echo=False,
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
            )
        elif db_path.startswith("sqlite://"):
            self.engine = create_engine(db_path, echo=False, connect_args={"check_same_thread": False})
        else:
            self.engine = create_engine(db_path, echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def create_sku(self, sku_code: str, name: str) -> SKU:
        session = self.get_session()
        try:
            sku = SKU(sku_code=sku_code, name=name)
            session.add(sku)
            session.commit()
            session.refresh(sku)
            return sku
        finally:
            session.close()

    def get_sku(self, sku_id: int) -> SKU | None:
        session = self.get_session()
        try:
            return session.query(SKU).filter(SKU.id == sku_id).first()
        finally:
            session.close()

    def get_stock(self, sku_id: int) -> Stock | None:
        session = self.get_session()
        try:
            return session.query(Stock).filter(Stock.sku_id == sku_id).first()
        finally:
            session.close()

    def create_stock(self, sku_id: int) -> Stock:
        session = self.get_session()
        try:
            stock = Stock(sku_id=sku_id, available=Decimal(0), reserved=Decimal(0))
            session.add(stock)
            session.commit()
            session.refresh(stock)
            return stock
        finally:
            session.close()

    def update_stock(
        self,
        sku_id: int,
        available: Decimal | None = None,
        reserved: Decimal | None = None,
        committed: Decimal | None = None,
    ) -> Stock:
        session = self.get_session()
        try:
            stock = session.query(Stock).filter(Stock.sku_id == sku_id).first()
            if not stock:
                raise ValueError(f"Stock not found for SKU {sku_id}")
            if available is not None:
                stock.available = available
            if reserved is not None:
                stock.reserved = reserved
            if committed is not None:
                stock.committed = committed
            session.commit()
            session.refresh(stock)
            return stock
        finally:
            session.close()

    def create_reservation(
        self,
        sku_id: int,
        quantity: Decimal,
        idempotency_key: str,
        expires_at: datetime,
    ) -> Reservation:
        session = self.get_session()
        try:
            reservation = Reservation(
                sku_id=sku_id,
                quantity=quantity,
                idempotency_key=idempotency_key,
                expires_at=expires_at,
            )
            session.add(reservation)
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def get_reservation(self, reservation_id: int) -> Reservation | None:
        session = self.get_session()
        try:
            return session.query(Reservation).filter(Reservation.id == reservation_id).first()
        finally:
            session.close()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        session = self.get_session()
        try:
            return (
                session.query(Reservation)
                .filter(Reservation.idempotency_key == idempotency_key)
                .first()
            )
        finally:
            session.close()

    def update_reservation(
        self, reservation_id: int, state: str, confirmed_at: datetime | None = None,
        cancelled_at: datetime | None = None
    ) -> Reservation:
        session = self.get_session()
        try:
            reservation = session.query(Reservation).filter(Reservation.id == reservation_id).first()
            if not reservation:
                raise ValueError(f"Reservation {reservation_id} not found")
            reservation.state = state
            if confirmed_at:
                reservation.confirmed_at = confirmed_at
            if cancelled_at:
                reservation.cancelled_at = cancelled_at
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def create_order(self, reservation_id: int, sku_id: int, quantity: Decimal, state: str) -> Order:
        session = self.get_session()
        try:
            order = Order(reservation_id=reservation_id, sku_id=sku_id, quantity=quantity, state=state)
            session.add(order)
            session.commit()
            session.refresh(order)
            return order
        finally:
            session.close()

    def list_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[Order], int]:
        session = self.get_session()
        try:
            total = session.query(Order).count()
            orders = session.query(Order).order_by(Order.created_at.desc()).limit(limit).offset(offset).all()
            return orders, total
        finally:
            session.close()
