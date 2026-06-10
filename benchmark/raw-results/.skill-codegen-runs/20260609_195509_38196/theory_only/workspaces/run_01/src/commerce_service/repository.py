from typing import Optional
from datetime import datetime

from sqlalchemy.orm import Session

from .models import (
    Base,
    SKUEntity,
    ReservationEntity,
    OrderEntity,
    ReservationStatus,
)


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # ========================================================================
    # SKU Operations
    # ========================================================================

    def create_sku(self, sku_id: str, name: str, quantity_on_hand: float) -> SKUEntity:
        sku = SKUEntity(id=sku_id, name=name, quantity_on_hand=quantity_on_hand)
        self.session.add(sku)
        self.session.commit()
        return sku

    def get_sku(self, sku_id: str) -> Optional[SKUEntity]:
        return self.session.query(SKUEntity).filter(SKUEntity.id == sku_id).first()

    def update_sku_quantity(self, sku_id: str, delta: float) -> Optional[SKUEntity]:
        sku = self.get_sku(sku_id)
        if not sku:
            return None
        sku.quantity_on_hand += delta
        self.session.commit()
        return sku

    # ========================================================================
    # Reservation Operations
    # ========================================================================

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: float,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> ReservationEntity:
        reservation = ReservationEntity(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
            status=ReservationStatus.PENDING,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get_reservation(self, reservation_id: str) -> Optional[ReservationEntity]:
        return (
            self.session.query(ReservationEntity)
            .filter(ReservationEntity.id == reservation_id)
            .first()
        )

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[ReservationEntity]:
        return (
            self.session.query(ReservationEntity)
            .filter(ReservationEntity.idempotency_key == key)
            .first()
        )

    def update_reservation_status(
        self, reservation_id: str, status: ReservationStatus
    ) -> Optional[ReservationEntity]:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.session.commit()
        return reservation

    # ========================================================================
    # Order Operations
    # ========================================================================

    def create_order(
        self,
        order_id: str,
        sku_id: str,
        quantity: float,
        reservation_id: str,
        idempotency_key: Optional[str] = None,
    ) -> OrderEntity:
        order = OrderEntity(
            id=order_id,
            sku_id=sku_id,
            quantity=quantity,
            reservation_id=reservation_id,
            idempotency_key=idempotency_key,
        )
        self.session.add(order)
        self.session.commit()
        return order

    def get_order(self, order_id: str) -> Optional[OrderEntity]:
        return self.session.query(OrderEntity).filter(OrderEntity.id == order_id).first()

    def get_order_by_idempotency_key(self, key: str) -> Optional[OrderEntity]:
        return (
            self.session.query(OrderEntity)
            .filter(OrderEntity.idempotency_key == key)
            .first()
        )

    def list_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[OrderEntity], int]:
        query = self.session.query(OrderEntity)
        total = query.count()
        offset = (page - 1) * page_size
        orders = query.offset(offset).limit(page_size).all()
        return orders, total

    # ========================================================================
    # Reserved Stock Calculation
    # ========================================================================

    def get_reserved_quantity(self, sku_id: str) -> float:
        result = (
            self.session.query(ReservationEntity)
            .filter(
                ReservationEntity.sku_id == sku_id,
                ReservationEntity.status == ReservationStatus.PENDING,
            )
            .all()
        )
        return sum(r.quantity for r in result)
