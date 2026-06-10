"""Data access layer for commerce operations."""

from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    Base,
    OrderModel,
    OrderStatus,
    ReservationModel,
    ReservationStatus,
    SKUModel,
)


class Repository:
    """Repository for data access."""

    def __init__(self, db_path: str = "commerce.db"):
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        """Get a database session."""
        return self.SessionLocal()

    def create_sku(self, sku_id: str, name: str, initial_stock: int) -> SKUModel:
        """Create a new SKU."""
        session = self.get_session()
        try:
            sku = SKUModel(id=sku_id, name=name, current_stock=initial_stock)
            session.add(sku)
            session.commit()
            session.refresh(sku)
            return sku
        finally:
            session.close()

    def get_sku(self, sku_id: str) -> Optional[SKUModel]:
        """Get a SKU by ID."""
        session = self.get_session()
        try:
            return session.query(SKUModel).filter(SKUModel.id == sku_id).first()
        finally:
            session.close()

    def list_skus(self) -> list[SKUModel]:
        """List all SKUs."""
        session = self.get_session()
        try:
            return session.query(SKUModel).all()
        finally:
            session.close()

    def adjust_stock(self, sku_id: str, adjustment: int) -> Optional[SKUModel]:
        """Adjust stock for a SKU."""
        session = self.get_session()
        try:
            sku = session.query(SKUModel).filter(SKUModel.id == sku_id).first()
            if sku:
                sku.current_stock += adjustment
                session.commit()
                session.refresh(sku)
            return sku
        finally:
            session.close()

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> ReservationModel:
        """Create a new reservation."""
        session = self.get_session()
        try:
            reservation = ReservationModel(
                id=reservation_id,
                sku_id=sku_id,
                quantity=quantity,
                status=ReservationStatus.PENDING,
                expires_at=expires_at,
                idempotency_key=idempotency_key,
                created_at=datetime.utcnow(),
            )
            session.add(reservation)
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def get_reservation(self, reservation_id: str) -> Optional[ReservationModel]:
        """Get a reservation by ID."""
        session = self.get_session()
        try:
            return (
                session.query(ReservationModel)
                .filter(ReservationModel.id == reservation_id)
                .first()
            )
        finally:
            session.close()

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[ReservationModel]:
        """Get a reservation by idempotency key."""
        session = self.get_session()
        try:
            return (
                session.query(ReservationModel)
                .filter(ReservationModel.idempotency_key == key)
                .first()
            )
        finally:
            session.close()

    def update_reservation_status(
        self, reservation_id: str, status: ReservationStatus
    ) -> Optional[ReservationModel]:
        """Update reservation status."""
        session = self.get_session()
        try:
            reservation = (
                session.query(ReservationModel)
                .filter(ReservationModel.id == reservation_id)
                .first()
            )
            if reservation:
                reservation.status = status
                session.commit()
                session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def create_order(
        self, order_id: str, reservation_id: str, status: OrderStatus = OrderStatus.PENDING
    ) -> OrderModel:
        """Create a new order."""
        session = self.get_session()
        try:
            order = OrderModel(
                id=order_id,
                reservation_id=reservation_id,
                status=status,
                created_at=datetime.utcnow(),
            )
            session.add(order)
            session.commit()
            session.refresh(order)
            return order
        finally:
            session.close()

    def get_order(self, order_id: str) -> Optional[OrderModel]:
        """Get an order by ID."""
        session = self.get_session()
        try:
            return session.query(OrderModel).filter(OrderModel.id == order_id).first()
        finally:
            session.close()

    def list_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[OrderModel], int]:
        """List orders with pagination. Returns (orders, total_count)."""
        session = self.get_session()
        try:
            total = session.query(OrderModel).count()
            orders = (
                session.query(OrderModel)
                .order_by(OrderModel.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return orders, total
        finally:
            session.close()

    def update_order_status(self, order_id: str, status: OrderStatus) -> Optional[OrderModel]:
        """Update order status."""
        session = self.get_session()
        try:
            order = session.query(OrderModel).filter(OrderModel.id == order_id).first()
            if order:
                order.status = status
                session.commit()
                session.refresh(order)
            return order
        finally:
            session.close()
