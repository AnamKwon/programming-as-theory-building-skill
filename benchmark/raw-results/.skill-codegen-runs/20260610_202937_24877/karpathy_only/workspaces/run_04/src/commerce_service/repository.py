from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base, SKUModel, ReservationModel, OrderModel

DATABASE_URL = "sqlite:///./commerce.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku: str, stock: int) -> SKUModel:
        db_sku = SKUModel(sku=sku, stock=stock)
        self.session.add(db_sku)
        self.session.commit()
        self.session.refresh(db_sku)
        return db_sku

    def get_sku_by_name(self, sku: str) -> SKUModel | None:
        return self.session.query(SKUModel).filter(SKUModel.sku == sku).first()

    def adjust_stock(self, sku: str, amount: int) -> SKUModel:
        db_sku = self.get_sku_by_name(sku)
        if db_sku:
            db_sku.stock += amount
            self.session.commit()
            self.session.refresh(db_sku)
        return db_sku

    def get_available_stock(self, sku: str) -> int:
        db_sku = self.get_sku_by_name(sku)
        if not db_sku:
            return 0

        reserved_quantity = self.session.query(ReservationModel).filter(
            ReservationModel.sku == sku,
            ReservationModel.status == "PENDING"
        ).with_entities(ReservationModel.quantity).all()

        reserved = sum(q[0] for q in reserved_quantity)
        return db_sku.stock - reserved

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> ReservationModel:
        db_reservation = ReservationModel(
            sku=sku, quantity=quantity, idempotency_key=idempotency_key, status="PENDING"
        )
        self.session.add(db_reservation)
        self.session.commit()
        self.session.refresh(db_reservation)
        return db_reservation

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> ReservationModel | None:
        return self.session.query(ReservationModel).filter(
            ReservationModel.idempotency_key == idempotency_key
        ).first()

    def get_reservation_by_id(self, reservation_id: int) -> ReservationModel | None:
        return self.session.query(ReservationModel).filter(
            ReservationModel.id == reservation_id
        ).first()

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> ReservationModel | None:
        db_reservation = self.get_reservation_by_id(reservation_id)
        if db_reservation:
            db_reservation.status = status
            self.session.commit()
            self.session.refresh(db_reservation)
        return db_reservation

    def create_order(self, reservation_id: int) -> OrderModel:
        db_order = OrderModel(reservation_id=reservation_id)
        self.session.add(db_order)
        self.session.commit()
        self.session.refresh(db_order)
        return db_order

    def get_orders(self, page: int, size: int) -> tuple[list[OrderModel], int]:
        query = self.session.query(OrderModel)
        total = query.count()
        orders = query.offset((page - 1) * size).limit(size).all()
        return orders, total
