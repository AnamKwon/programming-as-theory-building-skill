from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import SKUModel, ReservationModel, OrderModel, ReservationStatus


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # SKU operations
    def create_sku(self, code: str, name: str, description: Optional[str], stock_quantity: int) -> SKUModel:
        sku = SKUModel(code=code, name=name, description=description, stock_quantity=stock_quantity)
        self.session.add(sku)
        self.session.commit()
        self.session.refresh(sku)
        return sku

    def get_sku(self, sku_id: int) -> Optional[SKUModel]:
        return self.session.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def get_sku_by_code(self, code: str) -> Optional[SKUModel]:
        return self.session.query(SKUModel).filter(SKUModel.code == code).first()

    def update_sku_stock(self, sku_id: int, quantity_change: int) -> Optional[SKUModel]:
        sku = self.get_sku(sku_id)
        if not sku:
            return None
        sku.stock_quantity += quantity_change
        self.session.commit()
        self.session.refresh(sku)
        return sku

    # Reservation operations
    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
            status=ReservationStatus.PENDING,
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> Optional[ReservationModel]:
        return self.session.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationModel]:
        return self.session.query(ReservationModel).filter(ReservationModel.idempotency_key == idempotency_key).first()

    def update_reservation_status(self, reservation_id: int, status: ReservationStatus) -> Optional[ReservationModel]:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def list_pending_reservations_for_sku(self, sku_id: int) -> list[ReservationModel]:
        return self.session.query(ReservationModel).filter(
            ReservationModel.sku_id == sku_id,
            ReservationModel.status == ReservationStatus.PENDING,
        ).all()

    def list_expired_pending_reservations(self, now: datetime) -> list[ReservationModel]:
        return self.session.query(ReservationModel).filter(
            ReservationModel.status == ReservationStatus.PENDING,
            ReservationModel.expires_at <= now,
        ).all()

    # Order operations
    def create_order(self, reservation_ids: str, status: str) -> OrderModel:
        order = OrderModel(reservation_ids=reservation_ids, status=status)
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_order(self, order_id: int) -> Optional[OrderModel]:
        return self.session.query(OrderModel).filter(OrderModel.id == order_id).first()

    def list_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[OrderModel], int]:
        query = self.session.query(OrderModel)
        total = query.count()
        orders = query.limit(limit).offset(offset).all()
        return orders, total

    def update_order_status(self, order_id: int, status: str) -> Optional[OrderModel]:
        order = self.get_order(order_id)
        if not order:
            return None
        order.status = status
        self.session.commit()
        self.session.refresh(order)
        return order
