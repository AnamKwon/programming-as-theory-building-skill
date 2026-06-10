from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Optional
from .models import Base, SKUModel, ReservationModel, ReservationState, get_database_url


class Repository:
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    # SKU Operations

    def create_sku(self, sku: str, initial_quantity: int) -> SKUModel:
        session = self.get_session()
        try:
            sku_model = SKUModel(sku=sku, available_quantity=initial_quantity)
            session.add(sku_model)
            session.commit()
            session.refresh(sku_model)
            return sku_model
        finally:
            session.close()

    def get_sku(self, sku: str) -> Optional[SKUModel]:
        session = self.get_session()
        try:
            return session.query(SKUModel).filter(SKUModel.sku == sku).first()
        finally:
            session.close()

    def adjust_stock(self, sku: str, adjustment: int) -> Optional[SKUModel]:
        session = self.get_session()
        try:
            sku_model = session.query(SKUModel).filter(SKUModel.sku == sku).first()
            if not sku_model:
                return None
            sku_model.available_quantity += adjustment
            session.commit()
            session.refresh(sku_model)
            return sku_model
        finally:
            session.close()

    # Reservation Operations

    def create_reservation(
        self,
        reservation_id: str,
        sku: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> ReservationModel:
        session = self.get_session()
        try:
            reservation = ReservationModel(
                reservation_id=reservation_id,
                sku=sku,
                quantity=quantity,
                expires_at=expires_at,
                idempotency_key=idempotency_key,
            )
            session.add(reservation)
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def get_reservation(self, reservation_id: str) -> Optional[ReservationModel]:
        session = self.get_session()
        try:
            return session.query(ReservationModel).filter(
                ReservationModel.reservation_id == reservation_id
            ).first()
        finally:
            session.close()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationModel]:
        session = self.get_session()
        try:
            return session.query(ReservationModel).filter(
                ReservationModel.idempotency_key == idempotency_key
            ).first()
        finally:
            session.close()

    def update_reservation_state(
        self, reservation_id: str, state: ReservationState, confirmed_at: Optional[datetime] = None
    ) -> Optional[ReservationModel]:
        session = self.get_session()
        try:
            reservation = session.query(ReservationModel).filter(
                ReservationModel.reservation_id == reservation_id
            ).first()
            if not reservation:
                return None
            reservation.state = state
            if confirmed_at:
                reservation.confirmed_at = confirmed_at
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def reserve_stock(self, sku: str, quantity: int) -> bool:
        session = self.get_session()
        try:
            sku_model = session.query(SKUModel).filter(SKUModel.sku == sku).first()
            if not sku_model or sku_model.available_quantity < quantity:
                return False
            sku_model.available_quantity -= quantity
            sku_model.reserved_quantity += quantity
            session.commit()
            return True
        finally:
            session.close()

    def release_stock(self, sku: str, quantity: int) -> bool:
        session = self.get_session()
        try:
            sku_model = session.query(SKUModel).filter(SKUModel.sku == sku).first()
            if not sku_model:
                return False
            sku_model.reserved_quantity -= quantity
            sku_model.available_quantity += quantity
            session.commit()
            return True
        finally:
            session.close()

    def list_reservations(self, offset: int = 0, limit: int = 10) -> tuple[list[ReservationModel], int]:
        session = self.get_session()
        try:
            query = session.query(ReservationModel).order_by(ReservationModel.created_at.desc())
            total = query.count()
            reservations = query.offset(offset).limit(limit).all()
            return reservations, total
        finally:
            session.close()
