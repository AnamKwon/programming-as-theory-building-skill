from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from commerce_service.models import Base, SKU, Stock, Reservation, Order


class Repository:
    def __init__(self, db_url: str = "sqlite:///./test.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def create_sku(self, session: Session, code: str, name: str) -> SKU:
        sku = SKU(code=code, name=name)
        session.add(sku)
        session.commit()
        session.refresh(sku)
        return sku

    def get_sku_by_code(self, session: Session, code: str) -> SKU:
        return session.query(SKU).filter(SKU.code == code).first()

    def get_sku_by_id(self, session: Session, sku_id: str) -> SKU:
        return session.query(SKU).filter(SKU.id == sku_id).first()

    def get_or_create_stock(self, session: Session, sku_id: str) -> Stock:
        stock = session.query(Stock).filter(Stock.sku_id == sku_id).first()
        if not stock:
            stock = Stock(sku_id=sku_id, quantity=0, reserved=0)
            session.add(stock)
            session.commit()
            session.refresh(stock)
        return stock

    def adjust_stock(self, session: Session, sku_id: str, quantity: int) -> Stock:
        stock = self.get_or_create_stock(session, sku_id)
        stock.quantity += quantity
        session.commit()
        session.refresh(stock)
        return stock

    def get_stock(self, session: Session, sku_id: str) -> Stock:
        return self.get_or_create_stock(session, sku_id)

    def reserve_stock(self, session: Session, sku_id: str, quantity: int) -> bool:
        stock = self.get_stock(session, sku_id)
        available = stock.quantity - stock.reserved
        if available >= quantity:
            stock.reserved += quantity
            session.commit()
            session.refresh(stock)
            return True
        return False

    def unreserve_stock(self, session: Session, sku_id: str, quantity: int) -> None:
        stock = self.get_stock(session, sku_id)
        stock.reserved = max(0, stock.reserved - quantity)
        session.commit()

    def create_reservation(
        self, session: Session, sku_id: str, quantity: int, idempotency_key: str
    ) -> Reservation:
        expires_at = datetime.utcnow() + timedelta(hours=24)
        reservation = Reservation(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )
        session.add(reservation)
        session.commit()
        session.refresh(reservation)
        return reservation

    def get_reservation_by_id(self, session: Session, reservation_id: str) -> Reservation:
        return session.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(
        self, session: Session, idempotency_key: str
    ) -> Reservation:
        return (
            session.query(Reservation)
            .filter(Reservation.idempotency_key == idempotency_key)
            .first()
        )

    def confirm_reservation(self, session: Session, reservation_id: str) -> Reservation:
        reservation = self.get_reservation_by_id(session, reservation_id)
        reservation.confirmed = 1
        session.commit()
        session.refresh(reservation)
        return reservation

    def cancel_reservation(self, session: Session, reservation_id: str) -> Reservation:
        reservation = self.get_reservation_by_id(session, reservation_id)
        self.unreserve_stock(session, reservation.sku_id, reservation.quantity)
        session.delete(reservation)
        session.commit()
        return reservation

    def create_order(self, session: Session, reservation_id: str) -> Order:
        order = Order(reservation_id=reservation_id, status="PENDING")
        session.add(order)
        session.commit()
        session.refresh(order)
        return order

    def get_order_by_id(self, session: Session, order_id: str) -> Order:
        return session.query(Order).filter(Order.id == order_id).first()

    def get_orders_by_reservation_id(self, session: Session, reservation_id: str) -> Order:
        return session.query(Order).filter(Order.reservation_id == reservation_id).first()

    def update_order_status(self, session: Session, order_id: str, status: str) -> Order:
        order = self.get_order_by_id(session, order_id)
        order.status = status
        session.commit()
        session.refresh(order)
        return order

    def list_orders(self, session: Session, limit: int = 20, offset: int = 0) -> tuple:
        query = session.query(Order)
        total = query.count()
        orders = query.limit(limit).offset(offset).all()
        return orders, total
