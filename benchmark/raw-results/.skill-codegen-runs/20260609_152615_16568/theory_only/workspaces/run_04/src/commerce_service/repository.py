from datetime import datetime
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .models import Reservation, ReservationStatus, SKU


class RepositoryError(Exception):
    pass


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku: str, stock: int) -> SKU:
        sku_obj = SKU(sku=sku, stock=stock, reserved=0)
        self.db.add(sku_obj)
        self.db.commit()
        self.db.refresh(sku_obj)
        return sku_obj

    def get_sku_by_id(self, sku_id: int) -> Optional[SKU]:
        return self.db.execute(select(SKU).where(SKU.id == sku_id)).scalar_one_or_none()

    def get_sku_by_name(self, sku: str) -> Optional[SKU]:
        return self.db.execute(select(SKU).where(SKU.sku == sku)).scalar_one_or_none()

    def adjust_stock(self, sku_id: int, delta: int) -> Optional[SKU]:
        sku = self.get_sku_by_id(sku_id)
        if not sku:
            return None
        sku.stock += delta
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def create_reservation(
        self,
        order_id: str,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> Reservation:
        reservation = Reservation(
            order_id=order_id,
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            status=ReservationStatus.PENDING,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation_by_id(self, reservation_id: int) -> Optional[Reservation]:
        return self.db.execute(
            select(Reservation).where(Reservation.id == reservation_id)
        ).scalar_one_or_none()

    def get_reservation_by_order_id(self, order_id: str) -> Optional[Reservation]:
        return self.db.execute(
            select(Reservation).where(Reservation.order_id == order_id)
        ).scalar_one_or_none()

    def find_existing_reservation(
        self, sku_id: int, idempotency_key: str
    ) -> Optional[Reservation]:
        return self.db.execute(
            select(Reservation).where(
                and_(
                    Reservation.sku_id == sku_id,
                    Reservation.idempotency_key == idempotency_key,
                    Reservation.status == ReservationStatus.PENDING,
                )
            )
        ).scalar_one_or_none()

    def update_reservation_status(
        self, reservation_id: int, status: ReservationStatus, confirmed_at: Optional[datetime] = None
    ) -> Optional[Reservation]:
        reservation = self.get_reservation_by_id(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        if confirmed_at:
            reservation.confirmed_at = confirmed_at
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def increment_reserved_stock(self, sku_id: int, quantity: int) -> Optional[SKU]:
        sku = self.get_sku_by_id(sku_id)
        if not sku:
            return None
        sku.reserved += quantity
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def decrement_reserved_stock(self, sku_id: int, quantity: int) -> Optional[SKU]:
        sku = self.get_sku_by_id(sku_id)
        if not sku:
            return None
        sku.reserved = max(0, sku.reserved - quantity)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def list_orders(self, page: int, page_size: int) -> tuple[list[Reservation], int]:
        total = self.db.execute(
            select(Reservation).where(
                Reservation.status.in_([ReservationStatus.CONFIRMED, ReservationStatus.CANCELLED])
            )
        ).scalars().all()
        total_count = len(total)

        orders = self.db.execute(
            select(Reservation)
            .where(
                Reservation.status.in_([ReservationStatus.CONFIRMED, ReservationStatus.CANCELLED])
            )
            .order_by(Reservation.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()
        return orders, total_count

    def find_expired_reservations(self, now: datetime) -> list[Reservation]:
        return self.db.execute(
            select(Reservation).where(
                and_(
                    Reservation.status == ReservationStatus.PENDING,
                    Reservation.expires_at <= now,
                )
            )
        ).scalars().all()
