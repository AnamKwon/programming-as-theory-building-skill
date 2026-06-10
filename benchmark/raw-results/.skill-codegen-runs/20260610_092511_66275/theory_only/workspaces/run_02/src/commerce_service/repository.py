from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, OrderModel, ReservationModel, SKUModel, StockModel


class Repository:
    def __init__(self, database_url: str = "sqlite:///commerce.db"):
        self.engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def create_sku(self, sku_id: str, name: str, description: str | None = None) -> SKUModel:
        session = self.SessionLocal()
        try:
            sku = SKUModel(id=sku_id, name=name, description=description)
            session.add(sku)
            session.commit()
            return sku
        finally:
            session.close()

    def get_sku(self, sku_id: str) -> SKUModel | None:
        session = self.SessionLocal()
        try:
            return session.query(SKUModel).filter_by(id=sku_id).first()
        finally:
            session.close()

    def get_stock(self, sku_id: str) -> StockModel | None:
        session = self.SessionLocal()
        try:
            return session.query(StockModel).filter_by(sku_id=sku_id).first()
        finally:
            session.close()

    def create_stock(self, sku_id: str, quantity: int = 0) -> StockModel:
        session = self.SessionLocal()
        try:
            stock = StockModel(sku_id=sku_id, quantity_available=quantity)
            session.add(stock)
            session.commit()
            return stock
        finally:
            session.close()

    def update_stock(self, sku_id: str, quantity_delta: int) -> StockModel:
        session = self.SessionLocal()
        try:
            stock = session.query(StockModel).filter_by(sku_id=sku_id).with_for_update().first()
            if not stock:
                raise ValueError(f"Stock not found for SKU: {sku_id}")
            stock.quantity_available += quantity_delta
            stock.version += 1
            session.commit()
            return stock
        finally:
            session.close()

    def reserve_stock(self, sku_id: str, quantity: int) -> StockModel:
        session = self.SessionLocal()
        try:
            stock = session.query(StockModel).filter_by(sku_id=sku_id).with_for_update().first()
            if not stock:
                raise ValueError(f"Stock not found for SKU: {sku_id}")
            if stock.quantity_available < quantity:
                raise ValueError(
                    f"Insufficient stock: {stock.quantity_available} available, {quantity} requested"
                )
            stock.quantity_available -= quantity
            stock.quantity_reserved += quantity
            stock.version += 1
            session.commit()
            return stock
        finally:
            session.close()

    def release_stock(self, sku_id: str, quantity: int) -> StockModel:
        session = self.SessionLocal()
        try:
            stock = session.query(StockModel).filter_by(sku_id=sku_id).with_for_update().first()
            if not stock:
                raise ValueError(f"Stock not found for SKU: {sku_id}")
            stock.quantity_available += quantity
            stock.quantity_reserved -= quantity
            stock.version += 1
            session.commit()
            return stock
        finally:
            session.close()

    def create_reservation(self, reservation: ReservationModel) -> ReservationModel:
        session = self.SessionLocal()
        try:
            session.add(reservation)
            session.commit()
            return reservation
        finally:
            session.close()

    def get_reservation(self, reservation_id: str) -> ReservationModel | None:
        session = self.SessionLocal()
        try:
            return session.query(ReservationModel).filter_by(id=reservation_id).first()
        finally:
            session.close()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> ReservationModel | None:
        session = self.SessionLocal()
        try:
            return session.query(ReservationModel).filter_by(idempotency_key=idempotency_key).first()
        finally:
            session.close()

    def update_reservation_status(self, reservation_id: str, status: str) -> ReservationModel:
        session = self.SessionLocal()
        try:
            reservation = session.query(ReservationModel).filter_by(id=reservation_id).first()
            if not reservation:
                raise ValueError(f"Reservation not found: {reservation_id}")
            reservation.status = status
            session.commit()
            return reservation
        finally:
            session.close()

    def create_order(self, order: OrderModel) -> OrderModel:
        session = self.SessionLocal()
        try:
            session.add(order)
            session.commit()
            return order
        finally:
            session.close()

    def get_order(self, order_id: str) -> OrderModel | None:
        session = self.SessionLocal()
        try:
            return session.query(OrderModel).filter_by(id=order_id).first()
        finally:
            session.close()

    def get_order_by_reservation_id(self, reservation_id: str) -> OrderModel | None:
        session = self.SessionLocal()
        try:
            return session.query(OrderModel).filter_by(reservation_id=reservation_id).first()
        finally:
            session.close()

    def list_orders(self, skip: int = 0, limit: int = 10) -> tuple[list[OrderModel], int]:
        session = self.SessionLocal()
        try:
            query = session.query(OrderModel)
            total = query.count()
            orders = query.offset(skip).limit(limit).all()
            return orders, total
        finally:
            session.close()
