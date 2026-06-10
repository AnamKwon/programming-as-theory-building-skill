from datetime import datetime
from typing import Optional

from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from .models import OrderRecord, ReservationRecord, ReservationStatus, SKURecord


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # SKU operations
    def create_sku(self, sku_id: str, initial_stock: int) -> SKURecord:
        sku = SKURecord(id=sku_id, available_stock=initial_stock)
        self.session.add(sku)
        self.session.commit()
        return sku

    def get_sku(self, sku_id: str) -> Optional[SKURecord]:
        return self.session.execute(
            select(SKURecord).where(SKURecord.id == sku_id)
        ).scalar_one_or_none()

    def adjust_stock(self, sku_id: str, adjustment: int) -> Optional[SKURecord]:
        sku = self.get_sku(sku_id)
        if sku:
            sku.available_stock += adjustment
            self.session.commit()
        return sku

    # Reservation operations
    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> ReservationRecord:
        reservation = ReservationRecord(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get_reservation(self, reservation_id: str) -> Optional[ReservationRecord]:
        return self.session.execute(
            select(ReservationRecord).where(ReservationRecord.id == reservation_id)
        ).scalar_one_or_none()

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[ReservationRecord]:
        return self.session.execute(
            select(ReservationRecord).where(
                ReservationRecord.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()

    def get_pending_reservations_for_sku(self, sku_id: str) -> list[ReservationRecord]:
        return self.session.execute(
            select(ReservationRecord).where(
                and_(
                    ReservationRecord.sku_id == sku_id,
                    ReservationRecord.status == ReservationStatus.PENDING,
                    ReservationRecord.expires_at > datetime.utcnow(),
                )
            )
        ).scalars().all()

    def update_reservation_status(
        self, reservation_id: str, status: ReservationStatus
    ) -> Optional[ReservationRecord]:
        reservation = self.get_reservation(reservation_id)
        if reservation:
            reservation.status = status
            if status == ReservationStatus.CONFIRMED:
                reservation.confirmed_at = datetime.utcnow()
            self.session.commit()
        return reservation

    # Order operations
    def create_order(
        self, order_id: str, sku_id: str, quantity: int, reservation_id: str
    ) -> OrderRecord:
        order = OrderRecord(
            id=order_id,
            sku_id=sku_id,
            quantity=quantity,
            reservation_id=reservation_id,
        )
        self.session.add(order)
        self.session.commit()
        return order

    def get_orders(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[OrderRecord], int]:
        from sqlalchemy import func

        total = self.session.execute(
            select(func.count(OrderRecord.id))
        ).scalar() or 0

        query = select(OrderRecord).order_by(desc(OrderRecord.created_at))
        offset = (page - 1) * page_size
        records = self.session.execute(
            query.offset(offset).limit(page_size)
        ).scalars().all()

        return records, total
