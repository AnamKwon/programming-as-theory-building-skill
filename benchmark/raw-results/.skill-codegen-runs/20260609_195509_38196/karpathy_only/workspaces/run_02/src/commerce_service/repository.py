from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from contextlib import contextmanager

Base = declarative_base()


class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku_code = Column(String(50), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    available_quantity = Column(Integer, default=0, nullable=False)
    reserved_quantity = Column(Integer, default=0, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), default="reserved", nullable=False)
    idempotency_key = Column(String(100), unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)


class Repository:
    def __init__(self, db_url: str = "sqlite:///commerce.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    @contextmanager
    def get_session(self):
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_sku(self, sku_code: str, name: str) -> SKU:
        with self.get_session() as session:
            sku = SKU(sku_code=sku_code, name=name)
            session.add(sku)
            session.flush()
            sku_id = sku.id
        with self.get_session() as session:
            return session.query(SKU).filter(SKU.id == sku_id).first()

    def get_sku(self, sku_id: int) -> SKU | None:
        with self.get_session() as session:
            sku = session.query(SKU).filter(SKU.id == sku_id).first()
            if sku:
                session.expunge(sku)
            return sku

    def update_sku_stock(self, sku_id: int, available_delta: int, reserved_delta: int = 0) -> SKU | None:
        with self.get_session() as session:
            sku = session.query(SKU).filter(SKU.id == sku_id).first()
            if not sku:
                return None
            sku.available_quantity += available_delta
            sku.reserved_quantity += reserved_delta
            session.flush()
            sku_id = sku.id
        with self.get_session() as session:
            return session.query(SKU).filter(SKU.id == sku_id).first()

    def create_order(self, sku_id: int, quantity: int, idempotency_key: str | None = None) -> Order:
        with self.get_session() as session:
            order = Order(
                sku_id=sku_id,
                quantity=quantity,
                idempotency_key=idempotency_key,
                expires_at=datetime.utcnow() + timedelta(minutes=30),
            )
            session.add(order)
            session.flush()
            order_id = order.id
        with self.get_session() as session:
            return session.query(Order).filter(Order.id == order_id).first()

    def get_order(self, order_id: int) -> Order | None:
        with self.get_session() as session:
            order = session.query(Order).filter(Order.id == order_id).first()
            if order:
                session.expunge(order)
            return order

    def get_order_by_idempotency_key(self, idempotency_key: str) -> Order | None:
        with self.get_session() as session:
            order = session.query(Order).filter(Order.idempotency_key == idempotency_key).first()
            if order:
                session.expunge(order)
            return order

    def update_order_status(self, order_id: int, status: str) -> Order | None:
        with self.get_session() as session:
            order = session.query(Order).filter(Order.id == order_id).first()
            if not order:
                return None
            order.status = status
            if status == "confirmed":
                order.expires_at = None
            session.flush()
            order_id = order.id
        with self.get_session() as session:
            return session.query(Order).filter(Order.id == order_id).first()

    def list_orders(self, page: int = 1, per_page: int = 10) -> tuple[list[Order], int]:
        with self.get_session() as session:
            total = session.query(Order).count()
            offset = (page - 1) * per_page
            orders = session.query(Order).offset(offset).limit(per_page).all()
            for order in orders:
                session.expunge(order)
            return orders, total
