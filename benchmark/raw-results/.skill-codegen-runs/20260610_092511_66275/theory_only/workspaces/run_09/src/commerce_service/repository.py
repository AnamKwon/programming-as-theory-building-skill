from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, select, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

Base = declarative_base()


class SkuRecord(Base):
    __tablename__ = "skus"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    total_stock = Column(Integer, nullable=False)
    reserved_stock = Column(Integer, nullable=False, default=0)


class ReservationRecord(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    idempotency_key = Column(String(255), nullable=False, unique=True)
    status = Column(String(32), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False)


class OrderRecord(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    status = Column(String(32), nullable=False)
    created_at = Column(DateTime, nullable=False)


class Repository:
    def __init__(self, db_path: str = "sqlite:///commerce.db"):
        if db_path == "sqlite:///:memory:":
            self.engine = create_engine(
                db_path,
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
            )
        else:
            self.engine = create_engine(db_path)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    # SKU operations
    def create_sku(self, name: str, total_stock: int) -> SkuRecord:
        session = self.get_session()
        try:
            sku = SkuRecord(name=name, total_stock=total_stock, reserved_stock=0)
            session.add(sku)
            session.commit()
            session.refresh(sku)
            return sku
        finally:
            session.close()

    def get_sku(self, sku_id: int) -> SkuRecord | None:
        session = self.get_session()
        try:
            return session.query(SkuRecord).filter(SkuRecord.id == sku_id).first()
        finally:
            session.close()

    def adjust_stock(self, sku_id: int, adjustment: int) -> SkuRecord | None:
        session = self.get_session()
        try:
            sku = session.query(SkuRecord).filter(SkuRecord.id == sku_id).with_for_update().first()
            if not sku:
                return None
            sku.total_stock += adjustment
            session.commit()
            session.refresh(sku)
            return sku
        finally:
            session.close()

    # Reservation operations
    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str, ttl_minutes: int = 15
    ) -> ReservationRecord | None:
        session = self.get_session()
        try:
            sku = session.query(SkuRecord).filter(SkuRecord.id == sku_id).with_for_update().first()
            if not sku or sku.total_stock - sku.reserved_stock < quantity:
                return None

            reservation = ReservationRecord(
                sku_id=sku_id,
                quantity=quantity,
                idempotency_key=idempotency_key,
                status="pending",
                expires_at=datetime.utcnow() + timedelta(minutes=ttl_minutes),
                created_at=datetime.utcnow(),
            )
            session.add(reservation)

            sku.reserved_stock += quantity
            session.commit()
            session.refresh(reservation)
            return reservation
        except IntegrityError:
            session.rollback()
            return session.query(ReservationRecord).filter(
                ReservationRecord.idempotency_key == idempotency_key
            ).first()
        finally:
            session.close()

    def get_reservation(self, reservation_id: int) -> ReservationRecord | None:
        session = self.get_session()
        try:
            return session.query(ReservationRecord).filter(
                ReservationRecord.id == reservation_id
            ).first()
        finally:
            session.close()

    def confirm_reservation(self, reservation_id: int) -> ReservationRecord | None:
        session = self.get_session()
        try:
            reservation = session.query(ReservationRecord).filter(
                ReservationRecord.id == reservation_id
            ).with_for_update().first()
            if not reservation or reservation.status != "pending":
                return None

            if reservation.expires_at < datetime.utcnow():
                reservation.status = "cancelled"
                session.commit()
                return None

            reservation.status = "confirmed"
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def cancel_reservation(self, reservation_id: int) -> ReservationRecord | None:
        session = self.get_session()
        try:
            reservation = session.query(ReservationRecord).filter(
                ReservationRecord.id == reservation_id
            ).with_for_update().first()
            if not reservation or reservation.status != "pending":
                return None

            sku = session.query(SkuRecord).filter(
                SkuRecord.id == reservation.sku_id
            ).with_for_update().first()
            if sku:
                sku.reserved_stock -= reservation.quantity

            reservation.status = "cancelled"
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    # Order operations
    def create_order(self, reservation_id: int) -> OrderRecord | None:
        session = self.get_session()
        try:
            reservation = session.query(ReservationRecord).filter(
                ReservationRecord.id == reservation_id
            ).first()
            if not reservation or reservation.status != "confirmed":
                return None

            order = OrderRecord(
                reservation_id=reservation_id,
                status="reserved",
                created_at=datetime.utcnow(),
            )
            session.add(order)
            session.commit()
            session.refresh(order)
            return order
        finally:
            session.close()

    def get_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[OrderRecord], int]:
        session = self.get_session()
        try:
            total = session.query(OrderRecord).count()
            orders = session.query(OrderRecord).order_by(OrderRecord.id.desc()).limit(limit).offset(offset).all()
            return orders, total
        finally:
            session.close()

    def get_order(self, order_id: int) -> OrderRecord | None:
        session = self.get_session()
        try:
            return session.query(OrderRecord).filter(OrderRecord.id == order_id).first()
        finally:
            session.close()
