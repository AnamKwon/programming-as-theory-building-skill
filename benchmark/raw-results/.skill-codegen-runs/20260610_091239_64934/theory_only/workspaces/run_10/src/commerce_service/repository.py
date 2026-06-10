from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, OrderModel, ReservationModel, SKUModel


class Repository:
    def __init__(self, database_url: str = "sqlite:///commerce.db"):
        self.engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    # SKU Operations
    def create_sku(self, session: Session, sku_id: str, stock: int) -> SKUModel:
        sku = SKUModel(id=sku_id, total_stock=stock, reserved_stock=0, sold_stock=0)
        session.add(sku)
        session.commit()
        session.refresh(sku)
        return sku

    def get_sku(self, session: Session, sku_id: str) -> Optional[SKUModel]:
        return session.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def update_sku_stock(self, session: Session, sku_id: str, delta: int) -> SKUModel:
        sku = self.get_sku(session, sku_id)
        sku.total_stock += delta
        session.commit()
        session.refresh(sku)
        return sku

    def update_sku_reserved(self, session: Session, sku_id: str, delta: int) -> SKUModel:
        sku = self.get_sku(session, sku_id)
        sku.reserved_stock += delta
        session.commit()
        session.refresh(sku)
        return sku

    def update_sku_sold(self, session: Session, sku_id: str, delta: int) -> SKUModel:
        sku = self.get_sku(session, sku_id)
        sku.sold_stock += delta
        session.commit()
        session.refresh(sku)
        return sku

    # Reservation Operations
    def create_reservation(
        self,
        session: Session,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at,
        idempotency_key: Optional[str] = None,
    ) -> ReservationModel:
        reservation = ReservationModel(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
            status="active",
        )
        session.add(reservation)
        session.commit()
        session.refresh(reservation)
        return reservation

    def get_reservation(self, session: Session, reservation_id: str) -> Optional[ReservationModel]:
        return session.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()

    def get_reservation_by_idempotency_key(
        self, session: Session, idempotency_key: str
    ) -> Optional[ReservationModel]:
        return (
            session.query(ReservationModel)
            .filter(ReservationModel.idempotency_key == idempotency_key)
            .first()
        )

    def update_reservation_status(
        self, session: Session, reservation_id: str, status: str
    ) -> ReservationModel:
        reservation = self.get_reservation(session, reservation_id)
        reservation.status = status
        session.commit()
        session.refresh(reservation)
        return reservation

    # Order Operations
    def create_order(
        self,
        session: Session,
        order_id: str,
        sku_id: str,
        quantity: int,
        reservation_id: Optional[str] = None,
        status: str = "pending",
    ) -> OrderModel:
        order = OrderModel(
            id=order_id,
            sku_id=sku_id,
            quantity=quantity,
            reservation_id=reservation_id,
            status=status,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order

    def get_order(self, session: Session, order_id: str) -> Optional[OrderModel]:
        return session.query(OrderModel).filter(OrderModel.id == order_id).first()

    def list_orders(
        self, session: Session, skip: int = 0, limit: int = 20
    ) -> tuple[list[OrderModel], int]:
        query = session.query(OrderModel)
        total = query.count()
        orders = query.offset(skip).limit(limit).all()
        return orders, total

    def update_order_status(
        self, session: Session, order_id: str, status: str
    ) -> OrderModel:
        order = self.get_order(session, order_id)
        order.status = status
        session.commit()
        session.refresh(order)
        return order
