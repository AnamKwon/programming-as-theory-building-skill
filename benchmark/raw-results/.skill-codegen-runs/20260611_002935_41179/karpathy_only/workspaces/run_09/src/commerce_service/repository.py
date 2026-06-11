"""Database repository layer."""

from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from commerce_service.models import Base, OrderModel, ReservationModel, SKUModel

DATABASE_URL = "sqlite:///./commerce.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Repository:
    """Database repository for data access."""

    def __init__(self, db: Session):
        """Initialize repository with database session."""
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> SKUModel:
        """Create a new SKU."""
        sku_model = SKUModel(sku=sku, initial_stock=initial_stock, available_stock=initial_stock)
        self.db.add(sku_model)
        self.db.commit()
        self.db.refresh(sku_model)
        return sku_model

    def get_sku(self, sku: str) -> Optional[SKUModel]:
        """Get SKU by code."""
        return self.db.query(SKUModel).filter(SKUModel.sku == sku).first()

    def update_sku_stock(self, sku: str, amount: int) -> Optional[SKUModel]:
        """Update SKU available stock."""
        sku_model = self.get_sku(sku)
        if not sku_model:
            return None
        sku_model.available_stock += amount
        self.db.commit()
        self.db.refresh(sku_model)
        return sku_model

    def create_reservation(
        self,
        reservation_id: str,
        sku: str,
        quantity: int,
        idempotency_key: str,
        status: str,
        created_at: str,
    ) -> ReservationModel:
        """Create a new reservation."""
        reservation = ReservationModel(
            id=reservation_id,
            sku=sku,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status=status,
            created_at=created_at,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: str) -> Optional[ReservationModel]:
        """Get reservation by ID."""
        return self.db.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationModel]:
        """Get reservation by idempotency key."""
        return self.db.query(ReservationModel).filter(
            ReservationModel.idempotency_key == idempotency_key
        ).first()

    def update_reservation_status(self, reservation_id: str, status: str) -> Optional[ReservationModel]:
        """Update reservation status."""
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def create_order(
        self,
        order_id: str,
        reservation_id: str,
        sku: str,
        quantity: int,
        created_at: str,
    ) -> OrderModel:
        """Create a new order."""
        order = OrderModel(
            id=order_id,
            reservation_id=reservation_id,
            sku=sku,
            quantity=quantity,
            created_at=created_at,
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> tuple[list[OrderModel], int]:
        """Get paginated orders."""
        query = self.db.query(OrderModel)
        total = query.count()
        offset = (page - 1) * size
        orders = query.offset(offset).limit(size).all()
        return orders, total
