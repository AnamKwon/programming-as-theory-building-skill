"""Database repository layer."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import OrderModel, ReservationModel, SKUModel


class SKURepository:
    """Repository for SKU operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, sku: str, initial_stock: int) -> SKUModel:
        """Create a new SKU."""
        sku_model = SKUModel(sku=sku, total_stock=initial_stock, reserved_stock=0)
        self.session.add(sku_model)
        self.session.commit()
        self.session.refresh(sku_model)
        return sku_model

    def get_by_sku(self, sku: str) -> Optional[SKUModel]:
        """Get SKU by SKU code."""
        return self.session.query(SKUModel).filter(SKUModel.sku == sku).first()

    def update(self, sku_model: SKUModel) -> SKUModel:
        """Update a SKU."""
        self.session.merge(sku_model)
        self.session.commit()
        return self.session.query(SKUModel).filter(SKUModel.id == sku_model.id).first()


class ReservationRepository:
    """Repository for reservation operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
    ) -> ReservationModel:
        """Create a new reservation."""
        reservation = ReservationModel(
            sku_id=sku_id,
            quantity=quantity,
            status="PENDING",
            created_at=datetime.utcnow(),
            idempotency_key=idempotency_key,
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_by_id(self, reservation_id: int) -> Optional[ReservationModel]:
        """Get reservation by ID."""
        return (
            self.session.query(ReservationModel)
            .filter(ReservationModel.id == reservation_id)
            .first()
        )

    def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[ReservationModel]:
        """Get reservation by idempotency key."""
        return (
            self.session.query(ReservationModel)
            .filter(ReservationModel.idempotency_key == idempotency_key)
            .first()
        )

    def update(self, reservation: ReservationModel) -> ReservationModel:
        """Update a reservation."""
        self.session.merge(reservation)
        self.session.commit()
        return (
            self.session.query(ReservationModel)
            .filter(ReservationModel.id == reservation.id)
            .first()
        )


class OrderRepository:
    """Repository for order operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, reservation_id: int) -> OrderModel:
        """Create a new order."""
        order = OrderModel(reservation_id=reservation_id, created_at=datetime.utcnow())
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_by_id(self, order_id: int) -> Optional[OrderModel]:
        """Get order by ID."""
        return (
            self.session.query(OrderModel).filter(OrderModel.id == order_id).first()
        )

    def list_paginated(self, page: int = 1, size: int = 10) -> tuple[list[OrderModel], int]:
        """List orders with pagination."""
        query = self.session.query(OrderModel)
        total = query.count()
        offset = (page - 1) * size
        orders = query.offset(offset).limit(size).all()
        return orders, total
