"""Database repository layer."""

from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, select, desc, func
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, SKUModel, ReservationModel, OrderModel


class Repository:
    """Data access layer for commerce entities."""

    def __init__(self, db_url: str = "sqlite:///./commerce.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def init_db(self) -> None:
        """Initialize database tables."""
        Base.metadata.create_all(bind=self.engine)

    @contextmanager
    def get_session(self):
        """Get a database session context manager."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # SKU operations
    def create_sku(self, sku_code: str, qty: int) -> SKUModel:
        """Create a new SKU."""
        with self.get_session() as session:
            sku = SKUModel(sku_code=sku_code, qty_on_hand=qty)
            session.add(sku)
            session.flush()
            sku_id = sku.id
        # Re-fetch to ensure we have a detached instance with all attributes
        return self.get_sku_by_id(sku_id)

    def get_sku_by_id(self, sku_id: int) -> Optional[SKUModel]:
        """Get SKU by ID."""
        with self.get_session() as session:
            stmt = select(SKUModel).where(SKUModel.id == sku_id)
            result = session.execute(stmt).scalar_one_or_none()
            if result:
                session.expunge(result)
                return result
        return None

    def get_sku_by_code(self, sku_code: str) -> Optional[SKUModel]:
        """Get SKU by code."""
        with self.get_session() as session:
            stmt = select(SKUModel).where(SKUModel.sku_code == sku_code)
            result = session.execute(stmt).scalar_one_or_none()
            if result:
                session.expunge(result)
                return result
        return None

    def adjust_stock(self, sku_id: int, delta: int) -> SKUModel:
        """Adjust stock quantity."""
        with self.get_session() as session:
            sku = session.query(SKUModel).filter(SKUModel.id == sku_id).with_for_update().one_or_none()
            if not sku:
                raise ValueError(f"SKU {sku_id} not found")
            new_qty = sku.qty_on_hand + delta
            if new_qty < 0:
                raise ValueError("Insufficient stock for adjustment")
            sku.qty_on_hand = new_qty
            sku.updated_at = datetime.utcnow()
            session.flush()
            sku_id = sku.id
        return self.get_sku_by_id(sku_id)

    # Reservation operations
    def create_reservation(self, sku_id: int, qty: int, idempotency_key: str, expires_at: datetime) -> ReservationModel:
        """Create a reservation."""
        with self.get_session() as session:
            res = ReservationModel(
                sku_id=sku_id, qty=qty, idempotency_key=idempotency_key, expires_at=expires_at, status="pending"
            )
            session.add(res)
            session.flush()
            res_id = res.id
        return self.get_reservation_by_id(res_id)

    def get_reservation_by_id(self, reservation_id: int) -> Optional[ReservationModel]:
        """Get reservation by ID."""
        with self.get_session() as session:
            stmt = select(ReservationModel).where(ReservationModel.id == reservation_id)
            result = session.execute(stmt).scalar_one_or_none()
            if result:
                session.expunge(result)
                return result
        return None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationModel]:
        """Get reservation by idempotency key."""
        with self.get_session() as session:
            stmt = select(ReservationModel).where(ReservationModel.idempotency_key == idempotency_key)
            result = session.execute(stmt).scalar_one_or_none()
            if result:
                session.expunge(result)
                return result
        return None

    def confirm_reservation(self, reservation_id: int) -> ReservationModel:
        """Confirm a reservation."""
        with self.get_session() as session:
            res = session.query(ReservationModel).filter(ReservationModel.id == reservation_id).with_for_update().one()
            res.status = "confirmed"
            res.updated_at = datetime.utcnow()
            session.flush()
            res_id = res.id
        return self.get_reservation_by_id(res_id)

    def cancel_reservation(self, reservation_id: int) -> ReservationModel:
        """Cancel a reservation."""
        with self.get_session() as session:
            res = session.query(ReservationModel).filter(ReservationModel.id == reservation_id).with_for_update().one()
            res.status = "cancelled"
            res.updated_at = datetime.utcnow()
            session.flush()
            res_id = res.id
        return self.get_reservation_by_id(res_id)

    # Order operations
    def create_order(self, reservation_id: int, sku_id: int, qty: int) -> OrderModel:
        """Create an order from a reservation."""
        with self.get_session() as session:
            order = OrderModel(reservation_id=reservation_id, sku_id=sku_id, qty=qty, status="confirmed")
            session.add(order)
            session.flush()
            order_id = order.id
        return self.get_order_by_id(order_id)

    def get_order_by_id(self, order_id: int) -> Optional[OrderModel]:
        """Get order by ID."""
        with self.get_session() as session:
            stmt = select(OrderModel).where(OrderModel.id == order_id)
            result = session.execute(stmt).scalar_one_or_none()
            if result:
                session.expunge(result)
                return result
        return None

    def list_orders(self, offset: int = 0, limit: int = 50) -> tuple[list[OrderModel], int]:
        """List orders with pagination."""
        with self.get_session() as session:
            stmt = select(OrderModel).order_by(desc(OrderModel.created_at)).offset(offset).limit(limit)
            orders = session.execute(stmt).scalars().all()
            for o in orders:
                session.expunge(o)

            count_stmt = select(func.count()).select_from(OrderModel)
            total = session.execute(count_stmt).scalar()

        return orders, total
