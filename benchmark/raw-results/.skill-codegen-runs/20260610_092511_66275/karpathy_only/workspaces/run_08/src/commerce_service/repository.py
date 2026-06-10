from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, desc, func
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, ReservationRecord, ReservationState, SKURecord


class Repository:
    def __init__(self, db_url: str = "sqlite:///commerce.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    # ========================================================================
    # SKU Operations
    # ========================================================================

    def create_sku(self, sku_id: str, name: str, stock: int) -> SKURecord:
        session = self.get_session()
        try:
            sku = SKURecord(id=sku_id, name=name, available_stock=stock)
            session.add(sku)
            session.commit()
            session.refresh(sku)
            return sku
        finally:
            session.close()

    def get_sku(self, sku_id: str) -> Optional[SKURecord]:
        session = self.get_session()
        try:
            return session.query(SKURecord).filter(SKURecord.id == sku_id).first()
        finally:
            session.close()

    def update_sku_stock(self, sku_id: str, available_delta: int, reserved_delta: int = 0) -> Optional[SKURecord]:
        session = self.get_session()
        try:
            sku = session.query(SKURecord).filter(SKURecord.id == sku_id).with_for_update().first()
            if not sku:
                return None
            sku.available_stock = max(0, sku.available_stock + available_delta)
            sku.reserved_stock = max(0, sku.reserved_stock + reserved_delta)
            session.commit()
            session.refresh(sku)
            return sku
        finally:
            session.close()

    # ========================================================================
    # Reservation Operations
    # ========================================================================

    def create_reservation(
        self, reservation_id: str, sku_id: str, quantity: int, expires_at: datetime, idempotency_key: Optional[str] = None
    ) -> ReservationRecord:
        session = self.get_session()
        try:
            reservation = ReservationRecord(
                id=reservation_id, sku_id=sku_id, quantity=quantity, expires_at=expires_at, idempotency_key=idempotency_key
            )
            session.add(reservation)
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def get_reservation(self, reservation_id: str) -> Optional[ReservationRecord]:
        session = self.get_session()
        try:
            return session.query(ReservationRecord).filter(ReservationRecord.id == reservation_id).first()
        finally:
            session.close()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationRecord]:
        session = self.get_session()
        try:
            return session.query(ReservationRecord).filter(ReservationRecord.idempotency_key == idempotency_key).first()
        finally:
            session.close()

    def update_reservation_state(self, reservation_id: str, new_state: ReservationState) -> Optional[ReservationRecord]:
        session = self.get_session()
        try:
            reservation = session.query(ReservationRecord).filter(ReservationRecord.id == reservation_id).with_for_update().first()
            if not reservation:
                return None
            if new_state == ReservationState.CONFIRMED:
                reservation.confirmed_at = datetime.utcnow()
            reservation.state = new_state
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def get_reservations_by_sku(self, sku_id: str, state: Optional[ReservationState] = None) -> list[ReservationRecord]:
        session = self.get_session()
        try:
            query = session.query(ReservationRecord).filter(ReservationRecord.sku_id == sku_id)
            if state:
                query = query.filter(ReservationRecord.state == state)
            return query.all()
        finally:
            session.close()

    def get_expired_reservations(self) -> list[ReservationRecord]:
        session = self.get_session()
        try:
            return (
                session.query(ReservationRecord)
                .filter(
                    ReservationRecord.state == ReservationState.RESERVED,
                    ReservationRecord.expires_at < datetime.utcnow(),
                )
                .all()
            )
        finally:
            session.close()

    # ========================================================================
    # Order Operations (Reservations queried as orders)
    # ========================================================================

    def list_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[ReservationRecord], int]:
        session = self.get_session()
        try:
            total = session.query(func.count(ReservationRecord.id)).scalar() or 0
            orders = (
                session.query(ReservationRecord)
                .order_by(desc(ReservationRecord.created_at))
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return orders, total
        finally:
            session.close()
