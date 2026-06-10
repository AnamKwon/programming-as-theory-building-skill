import uuid
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Literal
from sqlalchemy.orm import declarative_base, Session, sessionmaker
from contextlib import contextmanager

Base = declarative_base()


class SKUModel(Base):
    __tablename__ = "skus"
    sku_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    current_stock = Column(Integer, nullable=False, default=0)


class ReservationModel(Base):
    __tablename__ = "reservations"
    reservation_id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class OrderModel(Base):
    __tablename__ = "orders"
    order_id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    reservation_id = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)


class Repository:
    def __init__(self, db_url: str = "sqlite:///./commerce.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        self.SessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)

    @contextmanager
    def get_session(self) -> Session:
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_sku(self, sku_id: str, name: str, initial_stock: int) -> dict:
        with self.get_session() as session:
            sku = SKUModel(sku_id=sku_id, name=name, current_stock=initial_stock)
            session.add(sku)
            return {"sku_id": sku.sku_id, "name": sku.name, "current_stock": sku.current_stock}

    def get_sku(self, sku_id: str) -> dict | None:
        with self.get_session() as session:
            sku = session.query(SKUModel).filter(SKUModel.sku_id == sku_id).first()
            if sku:
                return {"sku_id": sku.sku_id, "name": sku.name, "current_stock": sku.current_stock}
            return None

    def adjust_stock(self, sku_id: str, delta: int) -> dict:
        with self.get_session() as session:
            sku = session.query(SKUModel).filter(SKUModel.sku_id == sku_id).with_for_update().first()
            if not sku:
                raise ValueError(f"SKU {sku_id} not found")
            sku.current_stock += delta
            if sku.current_stock < 0:
                raise ValueError(f"Stock cannot be negative")
            session.commit()
            return {"sku_id": sku.sku_id, "name": sku.name, "current_stock": sku.current_stock}

    def create_reservation(self, sku_id: str, quantity: int, idempotency_key: str) -> dict:
        with self.get_session() as session:
            existing = session.query(ReservationModel).filter(
                ReservationModel.idempotency_key == idempotency_key
            ).first()
            if existing:
                return {
                    "reservation_id": existing.reservation_id,
                    "sku_id": existing.sku_id,
                    "quantity": existing.quantity,
                    "status": existing.status,
                    "expires_at": existing.expires_at,
                }

            sku = session.query(SKUModel).filter(SKUModel.sku_id == sku_id).with_for_update().first()
            if not sku:
                raise ValueError(f"SKU {sku_id} not found")
            if sku.current_stock < quantity:
                raise ValueError(f"Insufficient stock for {sku_id}")

            sku.current_stock -= quantity
            reservation_id = str(uuid.uuid4())
            now = datetime.utcnow()
            reservation = ReservationModel(
                reservation_id=reservation_id,
                sku_id=sku_id,
                quantity=quantity,
                status="created",
                idempotency_key=idempotency_key,
                created_at=now,
                expires_at=now + timedelta(minutes=15),
            )
            session.add(reservation)
            session.commit()
            return {
                "reservation_id": reservation.reservation_id,
                "sku_id": reservation.sku_id,
                "quantity": reservation.quantity,
                "status": reservation.status,
                "expires_at": reservation.expires_at,
            }

    def get_reservation(self, reservation_id: str) -> dict | None:
        with self.get_session() as session:
            res = session.query(ReservationModel).filter(
                ReservationModel.reservation_id == reservation_id
            ).first()
            if res:
                return {
                    "reservation_id": res.reservation_id,
                    "sku_id": res.sku_id,
                    "quantity": res.quantity,
                    "status": res.status,
                    "created_at": res.created_at,
                    "expires_at": res.expires_at,
                }
            return None

    def confirm_reservation(self, reservation_id: str) -> dict:
        with self.get_session() as session:
            res = session.query(ReservationModel).filter(
                ReservationModel.reservation_id == reservation_id
            ).with_for_update().first()
            if not res:
                raise ValueError(f"Reservation {reservation_id} not found")
            if res.status != "created":
                raise ValueError(f"Reservation is already {res.status}")
            if datetime.utcnow() > res.expires_at:
                res.status = "cancelled"
                session.commit()
                raise ValueError(f"Reservation has expired")

            res.status = "confirmed"
            order_id = str(uuid.uuid4())
            order = OrderModel(
                order_id=order_id,
                sku_id=res.sku_id,
                quantity=res.quantity,
                status="pending",
                reservation_id=reservation_id,
                created_at=datetime.utcnow(),
            )
            session.add(order)
            session.commit()
            return {
                "order_id": order.order_id,
                "sku_id": order.sku_id,
                "quantity": order.quantity,
                "status": order.status,
            }

    def cancel_reservation(self, reservation_id: str) -> dict:
        with self.get_session() as session:
            res = session.query(ReservationModel).filter(
                ReservationModel.reservation_id == reservation_id
            ).with_for_update().first()
            if not res:
                raise ValueError(f"Reservation {reservation_id} not found")
            if res.status in ("confirmed", "cancelled"):
                raise ValueError(f"Cannot cancel {res.status} reservation")

            sku = session.query(SKUModel).filter(SKUModel.sku_id == res.sku_id).with_for_update().first()
            sku.current_stock += res.quantity
            res.status = "cancelled"
            session.commit()
            return {"status": "cancelled"}

    def list_orders(self, limit: int = 10, offset: int = 0) -> dict:
        with self.get_session() as session:
            total = session.query(OrderModel).count()
            orders = session.query(OrderModel).order_by(OrderModel.created_at.desc()).limit(limit).offset(offset).all()
            items = [
                {
                    "order_id": o.order_id,
                    "sku_id": o.sku_id,
                    "quantity": o.quantity,
                    "status": o.status,
                    "created_at": o.created_at,
                }
                for o in orders
            ]
            return {
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
