"""Database access layer."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, DateTime, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class SKUModel(Base):
    __tablename__ = "skus"

    sku = Column(String, primary_key=True)
    initial_stock = Column(Integer, nullable=False)
    available_stock = Column(Integer, nullable=False)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    created_at = Column(DateTime, nullable=False)
    idempotency_key = Column(String, nullable=False, unique=True)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reservation_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)


class Database:
    def __init__(self, db_url: str = "sqlite:///commerce.db"):
        self.engine = create_engine(db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()


class SKURepository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku: str, initial_stock: int) -> SKUModel:
        sku_model = SKUModel(
            sku=sku,
            initial_stock=initial_stock,
            available_stock=initial_stock
        )
        self.session.add(sku_model)
        self.session.commit()
        return sku_model

    def get_sku(self, sku: str) -> Optional[SKUModel]:
        stmt = select(SKUModel).where(SKUModel.sku == sku)
        return self.session.scalars(stmt).first()

    def adjust_stock(self, sku: str, amount: int) -> Optional[SKUModel]:
        sku_model = self.get_sku(sku)
        if sku_model:
            sku_model.available_stock += amount
            self.session.commit()
        return sku_model


class ReservationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str, created_at: datetime
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku=sku,
            quantity=quantity,
            status="PENDING",
            created_at=created_at,
            idempotency_key=idempotency_key
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> Optional[ReservationModel]:
        return self.session.get(ReservationModel, reservation_id)

    def get_by_idempotency_key(self, key: str) -> Optional[ReservationModel]:
        stmt = select(ReservationModel).where(ReservationModel.idempotency_key == key)
        return self.session.scalars(stmt).first()

    def update_status(self, reservation_id: int, status: str) -> Optional[ReservationModel]:
        reservation = self.get_reservation(reservation_id)
        if reservation:
            reservation.status = status
            self.session.commit()
            self.session.refresh(reservation)
        return reservation


class OrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_order(self, reservation_id: int, created_at: datetime) -> OrderModel:
        order = OrderModel(
            reservation_id=reservation_id,
            created_at=created_at
        )
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def list_orders(self, page: int = 1, size: int = 10) -> tuple[list[OrderModel], int]:
        stmt = select(OrderModel)
        total = self.session.query(OrderModel).count()
        offset = (page - 1) * size
        stmt = stmt.offset(offset).limit(size)
        items = self.session.scalars(stmt).all()
        return list(items), total
