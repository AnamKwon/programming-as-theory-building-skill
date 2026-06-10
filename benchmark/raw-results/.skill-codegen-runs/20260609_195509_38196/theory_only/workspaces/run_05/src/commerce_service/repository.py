import uuid
from datetime import datetime, timedelta

from sqlalchemy import Column, DateTime, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DB_URL = "sqlite:///./commerce.db"
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    sku_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    stock = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    state = Column(String, default="pending", nullable=False)
    idempotency_key = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    reservation_id = Column(String, nullable=False, index=True)
    sku_id = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    state = Column(String, default="pending", nullable=False)
    idempotency_key = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(bind=engine)


def get_session() -> Session:
    """Get a database session."""
    return SessionLocal()


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # SKU operations
    def create_sku(self, sku_id: str, name: str, initial_stock: int) -> SKUModel:
        sku = SKUModel(
            id=str(uuid.uuid4()),
            sku_id=sku_id,
            name=name,
            stock=initial_stock,
        )
        self.session.add(sku)
        self.session.commit()
        return sku

    def get_sku(self, sku_id: str) -> SKUModel | None:
        return self.session.execute(
            select(SKUModel).where(SKUModel.sku_id == sku_id)
        ).scalar_one_or_none()

    def adjust_stock(self, sku_id: str, delta: int) -> SKUModel | None:
        sku = self.get_sku(sku_id)
        if not sku:
            return None
        sku.stock += delta
        self.session.commit()
        return sku

    # Reservation operations
    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str
    ) -> ReservationModel:
        reservation = ReservationModel(
            id=str(uuid.uuid4()),
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=datetime.utcnow() + timedelta(minutes=30),
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get_reservation(self, reservation_id: str) -> ReservationModel | None:
        return self.session.execute(
            select(ReservationModel).where(ReservationModel.id == reservation_id)
        ).scalar_one_or_none()

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> ReservationModel | None:
        return self.session.execute(
            select(ReservationModel).where(
                ReservationModel.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()

    def update_reservation_state(
        self, reservation_id: str, state: str, confirmed_at: datetime | None = None
    ) -> ReservationModel | None:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.state = state
        if confirmed_at:
            reservation.confirmed_at = confirmed_at
        self.session.commit()
        return reservation

    def get_expired_reservations(self) -> list[ReservationModel]:
        return self.session.execute(
            select(ReservationModel).where(
                (ReservationModel.state == "pending")
                & (ReservationModel.expires_at <= datetime.utcnow())
            )
        ).scalars().all()

    # Order operations
    def create_order(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
    ) -> OrderModel:
        order = OrderModel(
            id=str(uuid.uuid4()),
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
        )
        self.session.add(order)
        self.session.commit()
        return order

    def get_order(self, order_id: str) -> OrderModel | None:
        return self.session.execute(
            select(OrderModel).where(OrderModel.id == order_id)
        ).scalar_one_or_none()

    def get_order_by_idempotency_key(
        self, idempotency_key: str
    ) -> OrderModel | None:
        return self.session.execute(
            select(OrderModel).where(OrderModel.idempotency_key == idempotency_key)
        ).scalar_one_or_none()

    def update_order_state(self, order_id: str, state: str) -> OrderModel | None:
        order = self.get_order(order_id)
        if not order:
            return None
        order.state = state
        self.session.commit()
        return order

    def list_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[OrderModel], int]:
        query = select(OrderModel)
        total = self.session.query(OrderModel).count()
        orders = self.session.execute(
            query.limit(limit).offset(offset)
        ).scalars().all()
        return orders, total

    def close(self):
        self.session.close()
