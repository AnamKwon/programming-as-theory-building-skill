"""Database repository for persistence."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()


class SKU(Base):
    """SKU record."""
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku_code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)


class Stock(Base):
    """Stock level record."""
    __tablename__ = "stock"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False, unique=True)
    available = Column(Integer, default=0, nullable=False)
    reserved = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class Reservation(Base):
    """Reservation record."""
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    idempotency_key = Column(String(100), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class Order(Base):
    """Order record."""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    status = Column(String(20), default="pending", nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)


class OrderItem(Base):
    """Order line item."""
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)


class Repository:
    """Data access layer."""

    def __init__(self, database_url: str = "sqlite:///./commerce.db"):
        self.engine = create_engine(database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        """Get a database session."""
        return self.SessionLocal()

    def create_sku(self, session: Session, sku_code: str, name: str) -> SKU:
        """Create a new SKU."""
        sku = SKU(sku_code=sku_code, name=name)
        session.add(sku)
        session.commit()
        session.refresh(sku)
        return sku

    def get_sku_by_code(self, session: Session, sku_code: str) -> SKU | None:
        """Get SKU by code."""
        return session.query(SKU).filter(SKU.sku_code == sku_code).first()

    def get_or_create_stock(self, session: Session, sku_id: int) -> Stock:
        """Get or create stock record for a SKU."""
        stock = session.query(Stock).filter(Stock.sku_id == sku_id).first()
        if stock is None:
            stock = Stock(sku_id=sku_id, available=0, reserved=0)
            session.add(stock)
            session.commit()
            session.refresh(stock)
        return stock

    def adjust_stock(self, session: Session, sku_id: int, delta: int) -> Stock:
        """Adjust available stock."""
        stock = self.get_or_create_stock(session, sku_id)
        stock.available += delta
        session.commit()
        session.refresh(stock)
        return stock

    def get_stock(self, session: Session, sku_id: int) -> Stock | None:
        """Get stock record."""
        return session.query(Stock).filter(Stock.sku_id == sku_id).first()

    def reserve_stock(self, session: Session, sku_id: int, quantity: int) -> bool:
        """Try to reserve stock. Returns True if successful."""
        stock = self.get_stock(session, sku_id)
        if not stock or stock.available < quantity:
            return False

        stock.available -= quantity
        stock.reserved += quantity
        session.commit()
        return True

    def unreserve_stock(self, session: Session, sku_id: int, quantity: int) -> None:
        """Release reserved stock back to available."""
        stock = self.get_stock(session, sku_id)
        if stock:
            stock.available += quantity
            stock.reserved -= quantity
            session.commit()

    def create_reservation(
        self, session: Session, sku_id: int, quantity: int, idempotency_key: str
    ) -> Reservation:
        """Create a new reservation."""
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
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

    def get_reservation(self, session: Session, reservation_id: int) -> Reservation | None:
        """Get reservation by ID."""
        return session.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(
        self, session: Session, idempotency_key: str
    ) -> Reservation | None:
        """Get reservation by idempotency key."""
        return session.query(Reservation).filter(
            Reservation.idempotency_key == idempotency_key
        ).first()

    def update_reservation_status(
        self, session: Session, reservation_id: int, status: str
    ) -> Reservation | None:
        """Update reservation status."""
        reservation = self.get_reservation(session, reservation_id)
        if reservation:
            reservation.status = status
            session.commit()
            session.refresh(reservation)
        return reservation

    def get_expired_reservations(self, session: Session) -> list[Reservation]:
        """Get all expired pending reservations."""
        now = datetime.now(timezone.utc)
        return session.query(Reservation).filter(
            Reservation.status == "pending",
            Reservation.expires_at <= now,
        ).all()

    def create_order(self, session: Session) -> Order:
        """Create a new order."""
        order = Order(status="pending")
        session.add(order)
        session.commit()
        session.refresh(order)
        return order

    def create_order_item(
        self, session: Session, order_id: int, sku_id: int, quantity: int
    ) -> OrderItem:
        """Create an order line item."""
        item = OrderItem(order_id=order_id, sku_id=sku_id, quantity=quantity)
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

    def update_order_status(
        self, session: Session, order_id: int, status: str
    ) -> Order | None:
        """Update order status."""
        order = session.query(Order).filter(Order.id == order_id).first()
        if order:
            order.status = status
            session.commit()
            session.refresh(order)
        return order

    def get_order(self, session: Session, order_id: int) -> Order | None:
        """Get order by ID."""
        return session.query(Order).filter(Order.id == order_id).first()

    def get_order_items(self, session: Session, order_id: int) -> list[OrderItem]:
        """Get order items for an order."""
        return session.query(OrderItem).filter(OrderItem.order_id == order_id).all()

    def list_orders(
        self, session: Session, offset: int = 0, limit: int = 10
    ) -> tuple[list[Order], int]:
        """List orders with pagination."""
        query = session.query(Order).order_by(Order.created_at.desc())
        total = query.count()
        orders = query.offset(offset).limit(limit).all()
        return orders, total

    def get_sku_by_id(self, session: Session, sku_id: int) -> SKU | None:
        """Get SKU by ID."""
        return session.query(SKU).filter(SKU.id == sku_id).first()
