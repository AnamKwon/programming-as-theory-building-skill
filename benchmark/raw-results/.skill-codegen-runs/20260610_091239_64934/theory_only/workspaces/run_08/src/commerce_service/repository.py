import uuid
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import create_engine, Column, String, Integer, DateTime, select
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()


class SKURecord(Base):
    __tablename__ = "skus"
    sku_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)


class StockRecord(Base):
    __tablename__ = "stock"
    sku_id = Column(String, primary_key=True)
    available = Column(Integer, nullable=False, default=0)
    reserved = Column(Integer, nullable=False, default=0)


class ReservationRecord(Base):
    __tablename__ = "reservations"
    reservation_id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="active")
    idempotency_key = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class OrderRecord(Base):
    __tablename__ = "orders"
    order_id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="confirmed")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Repository:
    def __init__(self, db_url: str = "sqlite:///./commerce.db"):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def create_sku(self, session: Session, sku_id: str, name: str) -> SKURecord:
        sku = SKURecord(sku_id=sku_id, name=name)
        session.add(sku)
        session.commit()
        session.refresh(sku)
        return sku

    def get_sku(self, session: Session, sku_id: str) -> Optional[SKURecord]:
        return session.query(SKURecord).filter(SKURecord.sku_id == sku_id).first()

    def get_or_create_stock(self, session: Session, sku_id: str) -> StockRecord:
        stock = session.query(StockRecord).filter(StockRecord.sku_id == sku_id).first()
        if not stock:
            stock = StockRecord(sku_id=sku_id, available=0, reserved=0)
            session.add(stock)
            session.commit()
            session.refresh(stock)
        return stock

    def adjust_stock(self, session: Session, sku_id: str, quantity: int) -> StockRecord:
        stock = self.get_or_create_stock(session, sku_id)
        stock.available += quantity
        session.commit()
        session.refresh(stock)
        return stock

    def get_stock(self, session: Session, sku_id: str) -> Optional[StockRecord]:
        return session.query(StockRecord).filter(StockRecord.sku_id == sku_id).first()

    def create_reservation(
        self, session: Session, sku_id: str, quantity: int, idempotency_key: str
    ) -> ReservationRecord:
        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        reservation = ReservationRecord(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status="active",
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )
        session.add(reservation)
        session.commit()
        session.refresh(reservation)
        return reservation

    def get_reservation(self, session: Session, reservation_id: str) -> Optional[ReservationRecord]:
        return session.query(ReservationRecord).filter(ReservationRecord.reservation_id == reservation_id).first()

    def get_reservation_by_idempotency_key(
        self, session: Session, idempotency_key: str
    ) -> Optional[ReservationRecord]:
        return session.query(ReservationRecord).filter(ReservationRecord.idempotency_key == idempotency_key).first()

    def update_reservation_status(self, session: Session, reservation_id: str, status: str) -> ReservationRecord:
        reservation = self.get_reservation(session, reservation_id)
        if reservation:
            reservation.status = status
            session.commit()
            session.refresh(reservation)
        return reservation

    def create_order(self, session: Session, sku_id: str, quantity: int) -> OrderRecord:
        order_id = str(uuid.uuid4())
        order = OrderRecord(order_id=order_id, sku_id=sku_id, quantity=quantity, status="confirmed")
        session.add(order)
        session.commit()
        session.refresh(order)
        return order

    def get_order(self, session: Session, order_id: str) -> Optional[OrderRecord]:
        return session.query(OrderRecord).filter(OrderRecord.order_id == order_id).first()

    def list_orders(self, session: Session, limit: int = 10, cursor: Optional[str] = None) -> tuple[list[OrderRecord], Optional[str]]:
        query = session.query(OrderRecord).order_by(OrderRecord.created_at.desc())

        if cursor:
            cursor_date = datetime.fromisoformat(cursor)
            query = query.filter(OrderRecord.created_at < cursor_date)

        orders = query.limit(limit + 1).all()

        next_cursor = None
        if len(orders) > limit:
            next_cursor = orders[limit].created_at.isoformat()
            orders = orders[:limit]

        return orders, next_cursor

    def update_stock_reserved(self, session: Session, sku_id: str, delta: int) -> StockRecord:
        stock = self.get_or_create_stock(session, sku_id)
        stock.reserved += delta
        session.commit()
        session.refresh(stock)
        return stock
