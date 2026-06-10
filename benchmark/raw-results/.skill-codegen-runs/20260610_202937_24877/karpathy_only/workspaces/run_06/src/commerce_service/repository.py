from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .models import SKUModel, ReservationModel, OrderModel, ReservationStatus


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def get_sku_by_name(self, sku_name: str) -> Optional[SKUModel]:
        """Fetch SKU by name."""
        return self.db.scalar(select(SKUModel).where(SKUModel.sku == sku_name))

    def create_sku(self, sku_name: str, initial_stock: int) -> SKUModel:
        """Create a new SKU."""
        sku = SKUModel(sku=sku_name, initial_stock=initial_stock, available_stock=initial_stock)
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def adjust_stock(self, sku_id: int, amount: int) -> SKUModel:
        """Adjust stock for a SKU."""
        sku = self.db.scalar(select(SKUModel).where(SKUModel.id == sku_id))
        if not sku:
            raise ValueError(f"SKU with id {sku_id} not found")
        sku.available_stock += amount
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationModel]:
        """Fetch reservation by idempotency key."""
        return self.db.scalar(select(ReservationModel).where(ReservationModel.idempotency_key == idempotency_key))

    def create_reservation(
        self,
        sku_id: int,
        sku_name: str,
        quantity: int,
        idempotency_key: str,
    ) -> ReservationModel:
        """Create a new reservation and deduct stock."""
        sku = self.db.scalar(select(SKUModel).where(SKUModel.id == sku_id))
        if not sku:
            raise ValueError(f"SKU with id {sku_id} not found")

        if sku.available_stock < quantity:
            raise ValueError("Insufficient stock")

        sku.available_stock -= quantity

        reservation = ReservationModel(
            sku_id=sku_id,
            sku=sku_name,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status=ReservationStatus.PENDING,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> Optional[ReservationModel]:
        """Fetch reservation by id."""
        return self.db.scalar(select(ReservationModel).where(ReservationModel.id == reservation_id))

    def update_reservation_status(self, reservation_id: int, status: ReservationStatus) -> ReservationModel:
        """Update reservation status."""
        reservation = self.db.scalar(select(ReservationModel).where(ReservationModel.id == reservation_id))
        if not reservation:
            raise ValueError(f"Reservation with id {reservation_id} not found")
        reservation.status = status
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def restore_stock(self, sku_id: int, quantity: int) -> SKUModel:
        """Restore stock for a SKU."""
        return self.adjust_stock(sku_id, quantity)

    def create_order(self, reservation_id: int) -> OrderModel:
        """Create a new order from a reservation."""
        order = OrderModel(reservation_id=reservation_id)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_orders_paginated(self, page: int, size: int):
        """Fetch paginated orders."""
        offset = (page - 1) * size
        total = self.db.scalar(func.count(OrderModel.id))
        orders = self.db.scalars(
            select(OrderModel).offset(offset).limit(size).order_by(OrderModel.id.desc())
        ).all()
        return orders, total
