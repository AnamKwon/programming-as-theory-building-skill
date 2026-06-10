import uuid
from datetime import datetime, timedelta
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import IntegrityError

from .models import (
    Base,
    SKUModel,
    ReservationModel,
    OrderModel,
    ReservationStatus,
    OrderStatus,
)


class Repository:
    def __init__(self, db_url: str = "sqlite:///commerce.db"):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def create_sku(self, sku_id: str, available_stock: int) -> SKUModel:
        session = self.get_session()
        try:
            sku = SKUModel(id=sku_id, available_stock=available_stock, reserved_stock=0)
            session.add(sku)
            session.commit()
            session.refresh(sku)
            return sku
        finally:
            session.close()

    def get_sku(self, sku_id: str) -> SKUModel | None:
        session = self.get_session()
        try:
            stmt = select(SKUModel).where(SKUModel.id == sku_id)
            return session.execute(stmt).scalars().first()
        finally:
            session.close()

    def adjust_stock(self, sku_id: str, delta: int) -> SKUModel:
        session = self.get_session()
        try:
            sku = session.get(SKUModel, sku_id)
            if not sku:
                raise ValueError(f"SKU {sku_id} not found")
            sku.available_stock += delta
            if sku.available_stock < 0:
                raise ValueError("Stock cannot be negative")
            session.commit()
            session.refresh(sku)
            return sku
        finally:
            session.close()

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str, ttl_minutes: int = 15
    ) -> tuple[ReservationModel, bool]:
        """Create a reservation. Returns (reservation, is_new).
        If idempotency_key already exists, returns existing reservation with is_new=False."""
        session = self.get_session()
        try:
            stmt = select(ReservationModel).where(
                ReservationModel.idempotency_key == idempotency_key
            )
            existing = session.execute(stmt).scalars().first()
            if existing:
                return existing, False

            reservation_id = str(uuid.uuid4())
            expires_at = datetime.utcnow() + timedelta(minutes=ttl_minutes)

            reservation = ReservationModel(
                id=reservation_id,
                sku_id=sku_id,
                quantity=quantity,
                status=ReservationStatus.ACTIVE,
                idempotency_key=idempotency_key,
                expires_at=expires_at,
            )
            session.add(reservation)
            session.commit()
            session.refresh(reservation)
            return reservation, True
        finally:
            session.close()

    def get_reservation(self, reservation_id: str) -> ReservationModel | None:
        session = self.get_session()
        try:
            return session.get(ReservationModel, reservation_id)
        finally:
            session.close()

    def confirm_reservation(self, reservation_id: str) -> OrderModel:
        """Confirm a reservation and create an order."""
        session = self.get_session()
        try:
            reservation = session.get(ReservationModel, reservation_id)
            if not reservation:
                raise ValueError(f"Reservation {reservation_id} not found")

            if reservation.status != ReservationStatus.ACTIVE:
                raise ValueError(
                    f"Cannot confirm reservation in {reservation.status} status"
                )

            if datetime.utcnow() > reservation.expires_at:
                reservation.status = ReservationStatus.EXPIRED
                session.commit()
                raise ValueError("Reservation has expired")

            order_id = str(uuid.uuid4())
            order = OrderModel(
                id=order_id,
                reservation_id=reservation_id,
                sku_id=reservation.sku_id,
                quantity=reservation.quantity,
                status=OrderStatus.CONFIRMED,
            )
            reservation.status = ReservationStatus.CONFIRMED
            reservation.order_id = order_id

            session.add(order)
            session.commit()
            session.refresh(order)
            return order
        finally:
            session.close()

    def cancel_reservation(self, reservation_id: str) -> ReservationModel:
        """Cancel a reservation."""
        session = self.get_session()
        try:
            reservation = session.get(ReservationModel, reservation_id)
            if not reservation:
                raise ValueError(f"Reservation {reservation_id} not found")

            if reservation.status not in [ReservationStatus.ACTIVE, ReservationStatus.EXPIRED]:
                raise ValueError(
                    f"Cannot cancel reservation in {reservation.status} status"
                )

            reservation.status = ReservationStatus.CANCELLED
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def list_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[OrderModel], int]:
        """List orders with pagination. Returns (orders, total_count)."""
        session = self.get_session()
        try:
            stmt = select(OrderModel)
            total = session.query(OrderModel).count()

            offset = (page - 1) * page_size
            orders = (
                session.execute(stmt.offset(offset).limit(page_size))
                .scalars()
                .all()
            )
            return orders, total
        finally:
            session.close()

    def get_order(self, order_id: str) -> OrderModel | None:
        session = self.get_session()
        try:
            return session.get(OrderModel, order_id)
        finally:
            session.close()

    def get_reserved_stock(self, sku_id: str) -> int:
        """Calculate total reserved stock for a SKU (active reservations)."""
        session = self.get_session()
        try:
            stmt = select(ReservationModel).where(
                (ReservationModel.sku_id == sku_id)
                & (ReservationModel.status == ReservationStatus.ACTIVE)
                & (ReservationModel.expires_at > datetime.utcnow())
            )
            reservations = session.execute(stmt).scalars().all()
            return sum(r.quantity for r in reservations)
        finally:
            session.close()
