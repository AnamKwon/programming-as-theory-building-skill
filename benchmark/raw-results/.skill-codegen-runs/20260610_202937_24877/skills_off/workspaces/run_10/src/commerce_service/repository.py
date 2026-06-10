"""Data access layer."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import OrderModel, ReservationModel, SKUModel


class SKURepository:
    """Repository for SKU operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku: str, initial_stock: int) -> SKUModel:
        """Create a new SKU."""
        sku_model = SKUModel(sku=sku, available_stock=initial_stock)
        self.session.add(sku_model)
        self.session.commit()
        self.session.refresh(sku_model)
        return sku_model

    def get_sku(self, sku: str) -> Optional[SKUModel]:
        """Get SKU by code."""
        return self.session.query(SKUModel).filter(SKUModel.sku == sku).first()

    def update_stock(self, sku: str, amount: int) -> Optional[SKUModel]:
        """Update stock level."""
        sku_model = self.get_sku(sku)
        if not sku_model:
            return None
        sku_model.available_stock += amount
        self.session.commit()
        self.session.refresh(sku_model)
        return sku_model


class ReservationRepository:
    """Repository for Reservation operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> ReservationModel:
        """Create a new reservation."""
        reservation = ReservationModel(sku=sku, quantity=quantity, idempotency_key=idempotency_key, status="PENDING")
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> Optional[ReservationModel]:
        """Get reservation by ID."""
        return self.session.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationModel]:
        """Get reservation by idempotency key."""
        return self.session.query(ReservationModel).filter(ReservationModel.idempotency_key == idempotency_key).first()

    def update_reservation_status(self, reservation_id: int, status: str) -> Optional[ReservationModel]:
        """Update reservation status."""
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.session.commit()
        self.session.refresh(reservation)
        return reservation


class OrderRepository:
    """Repository for Order operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_order(self, reservation_id: int, sku: str, quantity: int) -> OrderModel:
        """Create a new order."""
        order = OrderModel(reservation_id=reservation_id, sku=sku, quantity=quantity)
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> tuple[list[OrderModel], int]:
        """Get paginated orders."""
        query = self.session.query(OrderModel)
        total = query.count()
        offset = (page - 1) * size
        orders = query.offset(offset).limit(size).all()
        return orders, total
