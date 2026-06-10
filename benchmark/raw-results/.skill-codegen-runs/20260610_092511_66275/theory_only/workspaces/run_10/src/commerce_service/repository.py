"""Data access layer."""

from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, Inventory, Order, Reservation, ReservationStatus, SKU

DATABASE_URL = "sqlite:///./commerce.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Repository:
    """Repository for data access."""

    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku_id: str, name: str) -> SKU:
        """Create a new SKU."""
        sku = SKU(id=sku_id, name=name)
        self.db.add(sku)
        inventory = Inventory(sku_id=sku_id, available_quantity=0, reserved_quantity=0)
        self.db.add(inventory)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def get_sku(self, sku_id: str) -> Optional[SKU]:
        """Get SKU by ID."""
        return self.db.execute(select(SKU).where(SKU.id == sku_id)).scalar_one_or_none()

    def get_inventory(self, sku_id: str) -> Optional[Inventory]:
        """Get inventory for a SKU."""
        return self.db.execute(select(Inventory).where(Inventory.sku_id == sku_id)).scalar_one_or_none()

    def adjust_inventory(self, sku_id: str, quantity_change: float) -> Inventory:
        """Adjust available inventory."""
        inventory = self.get_inventory(sku_id)
        if not inventory:
            raise ValueError(f"Inventory not found for SKU {sku_id}")
        inventory.available_quantity += quantity_change
        self.db.commit()
        self.db.refresh(inventory)
        return inventory

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        order_id: str,
        quantity: float,
        expires_at,
        idempotency_key: Optional[str] = None,
    ) -> Reservation:
        """Create a new reservation."""
        reservation = Reservation(
            id=reservation_id,
            sku_id=sku_id,
            order_id=order_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
            status=ReservationStatus.PENDING,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: str) -> Optional[Reservation]:
        """Get reservation by ID."""
        return self.db.execute(select(Reservation).where(Reservation.id == reservation_id)).scalar_one_or_none()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[Reservation]:
        """Get reservation by idempotency key."""
        return self.db.execute(
            select(Reservation).where(Reservation.idempotency_key == idempotency_key)
        ).scalar_one_or_none()

    def update_reservation_status(self, reservation_id: str, status: str) -> Reservation:
        """Update reservation status."""
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.status = status
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def reserve_inventory(self, sku_id: str, quantity: float) -> None:
        """Move quantity from available to reserved."""
        inventory = self.get_inventory(sku_id)
        if not inventory:
            raise ValueError(f"Inventory not found for SKU {sku_id}")
        inventory.available_quantity -= quantity
        inventory.reserved_quantity += quantity
        self.db.commit()

    def release_reserved_inventory(self, sku_id: str, quantity: float) -> None:
        """Move quantity from reserved back to available."""
        inventory = self.get_inventory(sku_id)
        if not inventory:
            raise ValueError(f"Inventory not found for SKU {sku_id}")
        inventory.reserved_quantity -= quantity
        inventory.available_quantity += quantity
        self.db.commit()

    def create_order(self, order_id: str) -> Order:
        """Create a new order."""
        order = Order(id=order_id)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID."""
        return self.db.execute(select(Order).where(Order.id == order_id)).scalar_one_or_none()

    def list_orders(self, skip: int = 0, limit: int = 10) -> tuple[list[Order], int]:
        """List orders with pagination."""
        query = select(Order).offset(skip).limit(limit)
        orders = self.db.execute(query).scalars().all()
        total = self.db.execute(select(Order)).scalars().all()
        return orders, len(total)

    def update_order_status(self, order_id: str, status: str) -> Order:
        """Update order status."""
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        order.status = status
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_reservations_by_order(self, order_id: str) -> list[Reservation]:
        """Get all reservations for an order."""
        return self.db.execute(select(Reservation).where(Reservation.order_id == order_id)).scalars().all()
