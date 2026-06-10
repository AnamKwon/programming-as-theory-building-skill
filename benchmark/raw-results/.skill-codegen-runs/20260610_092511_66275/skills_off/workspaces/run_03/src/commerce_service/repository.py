"""Data access layer for commerce service."""

from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .models import OrderModel, ReservationModel, ReservationStatus, SKUModel


class Repository:
    """Data access layer."""

    def __init__(self, session: Session):
        self.session = session

    # SKU operations

    def create_sku(self, sku_id: str, name: str, stock: int) -> SKUModel:
        sku = SKUModel(id=sku_id, name=name, stock=stock)
        self.session.add(sku)
        self.session.commit()
        return sku

    def get_sku(self, sku_id: str) -> SKUModel | None:
        return self.session.execute(
            select(SKUModel).where(SKUModel.id == sku_id)
        ).scalar_one_or_none()

    def update_sku_stock(self, sku_id: str, delta: int) -> SKUModel | None:
        sku = self.get_sku(sku_id)
        if sku:
            sku.stock += delta
            self.session.commit()
        return sku

    # Reservation operations

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: str | None = None,
    ) -> ReservationModel:
        reservation = ReservationModel(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get_reservation(self, reservation_id: str) -> ReservationModel | None:
        return self.session.execute(
            select(ReservationModel).where(ReservationModel.id == reservation_id)
        ).scalar_one_or_none()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> ReservationModel | None:
        return self.session.execute(
            select(ReservationModel).where(ReservationModel.idempotency_key == idempotency_key)
        ).scalar_one_or_none()

    def update_reservation_status(
        self, reservation_id: str, status: ReservationStatus
    ) -> ReservationModel | None:
        reservation = self.get_reservation(reservation_id)
        if reservation:
            reservation.status = status
            if status == ReservationStatus.CONFIRMED:
                reservation.confirmed_at = datetime.utcnow()
            self.session.commit()
        return reservation

    def get_pending_reservations_for_sku(self, sku_id: str) -> list[ReservationModel]:
        return self.session.execute(
            select(ReservationModel).where(
                and_(
                    ReservationModel.sku_id == sku_id,
                    ReservationModel.status == ReservationStatus.PENDING,
                )
            )
        ).scalars().all()

    # Order operations

    def create_order(
        self, order_id: str, reservation_id: str, sku_id: str, quantity: int
    ) -> OrderModel:
        order = OrderModel(
            id=order_id,
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
        )
        self.session.add(order)
        self.session.commit()
        return order

    def get_order(self, order_id: str) -> OrderModel | None:
        return self.session.execute(
            select(OrderModel).where(OrderModel.id == order_id)
        ).scalar_one_or_none()

    def get_order_by_reservation_id(self, reservation_id: str) -> OrderModel | None:
        return self.session.execute(
            select(OrderModel).where(OrderModel.reservation_id == reservation_id)
        ).scalar_one_or_none()

    def list_orders(self, page: int, page_size: int) -> tuple[list[OrderModel], int]:
        total = self.session.execute(select(func.count()).select_from(OrderModel)).scalar()
        orders = self.session.execute(
            select(OrderModel)
            .order_by(OrderModel.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        ).scalars().all()
        return orders, total


# Import func for list_orders
from sqlalchemy import func
