"""Repository layer for database access."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import OrderORM, ReservationORM, SkuORM


class SkuRepository:
    """Repository for SKU database operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, sku_code: str, stock_quantity: int = 0) -> SkuORM:
        """Create a new SKU."""
        sku = SkuORM(sku_code=sku_code, stock_quantity=stock_quantity)
        self.session.add(sku)
        self.session.commit()
        return sku

    def get_by_id(self, sku_id: int) -> Optional[SkuORM]:
        """Get SKU by ID."""
        return self.session.execute(
            select(SkuORM).where(SkuORM.id == sku_id)
        ).scalar_one_or_none()

    def get_by_code(self, sku_code: str) -> Optional[SkuORM]:
        """Get SKU by code."""
        return self.session.execute(
            select(SkuORM).where(SkuORM.sku_code == sku_code)
        ).scalar_one_or_none()

    def update_stock(self, sku_id: int, quantity_delta: int) -> Optional[SkuORM]:
        """Update stock quantity for a SKU."""
        sku = self.get_by_id(sku_id)
        if not sku:
            return None
        sku.stock_quantity += quantity_delta
        self.session.commit()
        return sku


class ReservationRepository:
    """Repository for reservation database operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> ReservationORM:
        """Create a new reservation."""
        reservation = ReservationORM(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            status="PENDING",
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get_by_id(self, reservation_id: int) -> Optional[ReservationORM]:
        """Get reservation by ID."""
        return self.session.execute(
            select(ReservationORM).where(ReservationORM.id == reservation_id)
        ).scalar_one_or_none()

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationORM]:
        """Get reservation by idempotency key."""
        return self.session.execute(
            select(ReservationORM).where(ReservationORM.idempotency_key == idempotency_key)
        ).scalar_one_or_none()

    def update_status(self, reservation_id: int, status: str) -> Optional[ReservationORM]:
        """Update reservation status."""
        reservation = self.get_by_id(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.session.commit()
        return reservation


class OrderRepository:
    """Repository for order database operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, reservation_id: int, status: str = "CREATED") -> OrderORM:
        """Create a new order."""
        order = OrderORM(reservation_id=reservation_id, status=status)
        self.session.add(order)
        self.session.commit()
        return order

    def get_by_id(self, order_id: int) -> Optional[OrderORM]:
        """Get order by ID."""
        return self.session.execute(
            select(OrderORM).where(OrderORM.id == order_id)
        ).scalar_one_or_none()

    def get_by_reservation_id(self, reservation_id: int) -> Optional[OrderORM]:
        """Get order by reservation ID."""
        return self.session.execute(
            select(OrderORM).where(OrderORM.reservation_id == reservation_id)
        ).scalar_one_or_none()

    def list_paginated(self, limit: int = 10, offset: int = 0) -> tuple[list[OrderORM], int]:
        """Get paginated list of orders with total count."""
        total = self.session.query(OrderORM).count()
        orders = self.session.execute(
            select(OrderORM).offset(offset).limit(limit + 1)
        ).scalars().all()
        return list(orders), total

    def update_status(self, order_id: int, status: str) -> Optional[OrderORM]:
        """Update order status."""
        order = self.get_by_id(order_id)
        if not order:
            return None
        order.status = status
        self.session.commit()
        return order
