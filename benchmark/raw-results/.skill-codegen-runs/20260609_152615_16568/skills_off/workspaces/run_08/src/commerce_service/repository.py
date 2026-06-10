from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, Order, OrderStatus, Reservation, ReservationStatus, SKU, Stock


class Repository:
    def __init__(self, db_url: str = "sqlite:///commerce.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    # SKU operations
    def create_sku(self, code: str, name: str) -> SKU:
        with self.get_session() as session:
            sku = SKU(code=code, name=name)
            session.add(sku)
            session.commit()
            session.refresh(sku)
            return sku

    def get_sku(self, sku_id: int) -> Optional[SKU]:
        with self.get_session() as session:
            return session.query(SKU).filter(SKU.id == sku_id).first()

    def get_sku_by_code(self, code: str) -> Optional[SKU]:
        with self.get_session() as session:
            return session.query(SKU).filter(SKU.code == code).first()

    # Stock operations
    def get_stock(self, sku_id: int) -> Optional[Stock]:
        with self.get_session() as session:
            stock = session.query(Stock).filter(Stock.sku_id == sku_id).first()
            if stock:
                return Stock(
                    sku_id=stock.sku_id,
                    available_qty=stock.available_qty,
                    reserved_qty=stock.reserved_qty,
                )
            return None

    def initialize_stock(self, sku_id: int) -> Stock:
        with self.get_session() as session:
            stock = Stock(sku_id=sku_id, available_qty=0, reserved_qty=0)
            session.add(stock)
            session.commit()
            return stock

    def adjust_stock(self, sku_id: int, available_delta: int) -> Optional[Stock]:
        with self.get_session() as session:
            stock = session.query(Stock).filter(Stock.sku_id == sku_id).first()
            if not stock:
                return None
            stock.available_qty += available_delta
            session.commit()
            session.refresh(stock)
            return stock

    def reserve_stock(self, sku_id: int, quantity: int) -> bool:
        with self.get_session() as session:
            stock = session.query(Stock).filter(Stock.sku_id == sku_id).first()
            if not stock or stock.available_qty < quantity:
                return False
            stock.available_qty -= quantity
            stock.reserved_qty += quantity
            session.commit()
            return True

    def release_reserved_stock(self, sku_id: int, quantity: int) -> bool:
        with self.get_session() as session:
            stock = session.query(Stock).filter(Stock.sku_id == sku_id).first()
            if not stock or stock.reserved_qty < quantity:
                return False
            stock.reserved_qty -= quantity
            stock.available_qty += quantity
            session.commit()
            return True

    # Reservation operations
    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> Reservation:
        with self.get_session() as session:
            reservation = Reservation(
                sku_id=sku_id,
                quantity=quantity,
                idempotency_key=idempotency_key,
                expires_at=expires_at,
                status=ReservationStatus.PENDING,
            )
            session.add(reservation)
            session.commit()
            session.refresh(reservation)
            return reservation

    def get_reservation(self, reservation_id: int) -> Optional[Reservation]:
        with self.get_session() as session:
            return session.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[Reservation]:
        with self.get_session() as session:
            return (
                session.query(Reservation)
                .filter(Reservation.idempotency_key == key)
                .first()
            )

    def update_reservation_status(
        self, reservation_id: int, status: ReservationStatus
    ) -> Optional[Reservation]:
        with self.get_session() as session:
            reservation = session.query(Reservation).filter(
                Reservation.id == reservation_id
            ).first()
            if not reservation:
                return None
            reservation.status = status
            session.commit()
            session.refresh(reservation)
            return reservation

    def get_expired_reservations(self, now: datetime) -> list[Reservation]:
        with self.get_session() as session:
            return (
                session.query(Reservation)
                .filter(
                    Reservation.status == ReservationStatus.PENDING,
                    Reservation.expires_at <= now,
                )
                .all()
            )

    # Order operations
    def create_order(
        self, reservation_id: int, sku_id: int, quantity: int
    ) -> Order:
        with self.get_session() as session:
            order = Order(
                reservation_id=reservation_id,
                sku_id=sku_id,
                quantity=quantity,
                status=OrderStatus.PENDING,
            )
            session.add(order)
            session.commit()
            session.refresh(order)
            return order

    def get_order(self, order_id: int) -> Optional[Order]:
        with self.get_session() as session:
            return session.query(Order).filter(Order.id == order_id).first()

    def update_order_status(self, order_id: int, status: OrderStatus) -> Optional[Order]:
        with self.get_session() as session:
            order = session.query(Order).filter(Order.id == order_id).first()
            if not order:
                return None
            order.status = status
            if status == OrderStatus.CONFIRMED:
                order.confirmed_at = datetime.utcnow()
            session.commit()
            session.refresh(order)
            return order

    def list_orders(self, offset: int = 0, limit: int = 10) -> tuple[list[Order], int]:
        with self.get_session() as session:
            query = session.query(Order)
            total = query.count()
            orders = query.offset(offset).limit(limit).all()
            return orders, total

    def get_order_by_reservation(self, reservation_id: int) -> Optional[Order]:
        with self.get_session() as session:
            return (
                session.query(Order)
                .filter(Order.reservation_id == reservation_id)
                .first()
            )
