from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .models import SKUModel, ReservationModel, OrderModel, ReservationStatus


class RepositoryError(Exception):
    pass


class SKUNotFoundError(RepositoryError):
    pass


class DuplicateIdempotencyKeyError(RepositoryError):
    pass


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku_id: str, name: str) -> SKUModel:
        sku = SKUModel(sku_id=sku_id, name=name, available=0, reserved=0)
        self.session.add(sku)
        self.session.commit()
        self.session.refresh(sku)
        return sku

    def get_sku(self, sku_id: str) -> SKUModel:
        stmt = select(SKUModel).where(SKUModel.sku_id == sku_id)
        sku = self.session.execute(stmt).scalar_one_or_none()
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")
        return sku

    def adjust_stock(self, sku_id: str, quantity: int) -> SKUModel:
        sku = self.get_sku(sku_id)
        sku.available += quantity
        self.session.commit()
        self.session.refresh(sku)
        return sku

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> ReservationModel:
        try:
            reservation = ReservationModel(
                reservation_id=reservation_id,
                sku_id=sku_id,
                quantity=quantity,
                idempotency_key=idempotency_key,
                expires_at=expires_at,
            )
            self.session.add(reservation)
            self.session.commit()
            self.session.refresh(reservation)
            return reservation
        except IntegrityError:
            self.session.rollback()
            raise DuplicateIdempotencyKeyError(f"Idempotency key already used: {idempotency_key}")

    def get_reservation_by_key(self, idempotency_key: str) -> ReservationModel | None:
        stmt = select(ReservationModel).where(ReservationModel.idempotency_key == idempotency_key)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_reservation(self, reservation_id: str) -> ReservationModel:
        stmt = select(ReservationModel).where(ReservationModel.reservation_id == reservation_id)
        reservation = self.session.execute(stmt).scalar_one_or_none()
        if not reservation:
            raise RepositoryError(f"Reservation {reservation_id} not found")
        return reservation

    def update_reservation_status(
        self, reservation_id: str, status: ReservationStatus
    ) -> ReservationModel:
        reservation = self.get_reservation(reservation_id)
        reservation.status = status
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def create_order(
        self, order_id: str, reservation_id: str, sku_id: str, quantity: int
    ) -> OrderModel:
        order = OrderModel(
            order_id=order_id,
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
        )
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_orders(self, offset: int = 0, limit: int = 10) -> tuple[list[OrderModel], int]:
        stmt_count = select(func.count()).select_from(OrderModel)
        total = self.session.execute(stmt_count).scalar()

        stmt = select(OrderModel).offset(offset).limit(limit)
        orders = self.session.execute(stmt).scalars().all()

        return orders, total

    def mark_expired_reservations(self, now: datetime) -> int:
        stmt = select(ReservationModel).where(
            (ReservationModel.expires_at <= now)
            & (ReservationModel.status == ReservationStatus.PENDING)
        )
        expired = self.session.execute(stmt).scalars().all()

        for reservation in expired:
            reservation.status = ReservationStatus.EXPIRED

        self.session.commit()
        return len(expired)
