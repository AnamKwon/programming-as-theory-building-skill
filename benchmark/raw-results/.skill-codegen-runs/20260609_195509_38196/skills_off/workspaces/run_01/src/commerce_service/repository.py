from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import (
    OrderStatus,
    OrderTable,
    ReservationStatus,
    ReservationTable,
    SKUTable,
)


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku_id: str, name: str, available_stock: int) -> SKUTable:
        sku = SKUTable(
            id=sku_id, name=name, available_stock=available_stock, reserved_stock=0
        )
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def get_sku(self, sku_id: str) -> Optional[SKUTable]:
        return self.db.query(SKUTable).filter(SKUTable.id == sku_id).first()

    def update_sku_stock(
        self, sku_id: str, available_delta: int, reserved_delta: int
    ) -> Optional[SKUTable]:
        sku = self.get_sku(sku_id)
        if not sku:
            return None
        sku.available_stock += available_delta
        sku.reserved_stock += reserved_delta
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def create_reservation(
        self, reservation_id: str, sku_id: str, quantity: int, expires_at: datetime
    ) -> ReservationTable:
        reservation = ReservationTable(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status=ReservationStatus.PENDING,
            expires_at=expires_at,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: str) -> Optional[ReservationTable]:
        return (
            self.db.query(ReservationTable)
            .filter(ReservationTable.id == reservation_id)
            .first()
        )

    def confirm_reservation(
        self, reservation_id: str
    ) -> Optional[ReservationTable]:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = ReservationStatus.CONFIRMED
        reservation.confirmed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def cancel_reservation(
        self, reservation_id: str
    ) -> Optional[ReservationTable]:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = ReservationStatus.CANCELLED
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def create_order(
        self,
        order_id: str,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        idempotency_key: Optional[str] = None,
    ) -> OrderTable:
        order = OrderTable(
            id=order_id,
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status=OrderStatus.PENDING,
            idempotency_key=idempotency_key,
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_order(self, order_id: str) -> Optional[OrderTable]:
        return self.db.query(OrderTable).filter(OrderTable.id == order_id).first()

    def get_order_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[OrderTable]:
        return (
            self.db.query(OrderTable)
            .filter(OrderTable.idempotency_key == idempotency_key)
            .first()
        )

    def confirm_order(self, order_id: str) -> Optional[OrderTable]:
        order = self.get_order(order_id)
        if not order:
            return None
        order.status = OrderStatus.CONFIRMED
        order.confirmed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(order)
        return order

    def list_orders(self, skip: int = 0, limit: int = 20) -> tuple[list[OrderTable], int]:
        query = self.db.query(OrderTable)
        total = query.count()
        orders = query.offset(skip).limit(limit).all()
        return orders, total

    def get_expired_pending_reservations(
        self, as_of: datetime
    ) -> list[ReservationTable]:
        return (
            self.db.query(ReservationTable)
            .filter(
                ReservationTable.status == ReservationStatus.PENDING,
                ReservationTable.expires_at < as_of,
            )
            .all()
        )
