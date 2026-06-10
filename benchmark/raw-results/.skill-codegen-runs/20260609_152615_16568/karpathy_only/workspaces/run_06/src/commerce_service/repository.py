from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # SKU operations

    def create_sku(self, sku_code: str, name: str, initial_stock: int) -> models.SKUModel:
        sku = models.SKUModel(
            sku_code=sku_code, name=name, stock_quantity=initial_stock
        )
        self.session.add(sku)
        self.session.flush()
        return sku

    def get_sku(self, sku_id: int) -> Optional[models.SKUModel]:
        return self.session.execute(
            select(models.SKUModel).where(models.SKUModel.id == sku_id)
        ).scalar_one_or_none()

    def adjust_sku_stock(self, sku_id: int, quantity: int) -> models.SKUModel:
        sku = self.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        sku.stock_quantity += quantity
        self.session.flush()
        return sku

    # Reservation operations

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[models.ReservationModel]:
        return self.session.execute(
            select(models.ReservationModel).where(
                models.ReservationModel.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()

    def get_reservation(self, reservation_id: int) -> Optional[models.ReservationModel]:
        return self.session.execute(
            select(models.ReservationModel).where(models.ReservationModel.id == reservation_id)
        ).scalar_one_or_none()

    def get_reservation_by_public_id(
        self, reservation_id: str
    ) -> Optional[models.ReservationModel]:
        return self.session.execute(
            select(models.ReservationModel).where(
                models.ReservationModel.reservation_id == reservation_id
            )
        ).scalar_one_or_none()

    def create_reservation(
        self,
        reservation_id: str,
        idempotency_key: str,
        expires_at,
        items: list[tuple[int, int]],
    ) -> models.ReservationModel:
        reservation = models.ReservationModel(
            reservation_id=reservation_id,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            status=models.ReservationStatus.PENDING,
        )
        self.session.add(reservation)
        self.session.flush()

        for sku_id, quantity in items:
            item = models.ReservationItemModel(
                reservation_id=reservation.id, sku_id=sku_id, quantity=quantity
            )
            self.session.add(item)

        self.session.flush()
        return reservation

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> models.ReservationModel:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.status = status
        self.session.flush()
        return reservation

    # Order operations

    def get_order_by_public_id(self, order_id: str) -> Optional[models.OrderModel]:
        return self.session.execute(
            select(models.OrderModel).where(models.OrderModel.order_id == order_id)
        ).scalar_one_or_none()

    def get_order(self, order_id: int) -> Optional[models.OrderModel]:
        return self.session.execute(
            select(models.OrderModel).where(models.OrderModel.id == order_id)
        ).scalar_one_or_none()

    def list_orders(self, skip: int = 0, limit: int = 10) -> tuple[list[models.OrderModel], int]:
        query = select(models.OrderModel).offset(skip).limit(limit)
        orders = self.session.execute(query).scalars().all()

        count_query = select(models.OrderModel.__table__)
        total = self.session.execute(
            select(models.OrderModel)
        ).scalars().all().__len__()

        return orders, total

    def create_order(
        self, order_id: str, reservation_id: int
    ) -> models.OrderModel:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        order = models.OrderModel(
            order_id=order_id,
            reservation_id=reservation_id,
            status=models.OrderStatus.PENDING,
        )
        self.session.add(order)
        self.session.flush()

        for item in reservation.items:
            order_item = models.OrderItemModel(
                order_id=order.id, sku_id=item.sku_id, quantity=item.quantity
            )
            self.session.add(order_item)

        self.session.flush()
        return order

    def update_order_status(
        self, order_id: int, status: str
    ) -> models.OrderModel:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        order.status = status
        self.session.flush()
        return order

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()
