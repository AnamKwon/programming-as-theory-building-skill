from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Order, Reservation, ReservationStatus, SKU


class RepositoryError(Exception):
    pass


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku: str, name: str, initial_stock: int) -> SKU:
        db_sku = SKU(sku=sku, name=name, total_stock=initial_stock, reserved_stock=0)
        self.session.add(db_sku)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise RepositoryError(f"SKU {sku} already exists")
        return db_sku

    def get_sku(self, sku: str) -> SKU | None:
        return self.session.execute(select(SKU).where(SKU.sku == sku)).scalar_one_or_none()

    def update_sku_stock(self, sku: str, total_delta: int):
        db_sku = self.get_sku(sku)
        if not db_sku:
            raise RepositoryError(f"SKU {sku} not found")
        db_sku.total_stock += total_delta
        self.session.commit()

    def create_reservation(
        self,
        reservation_id: str,
        sku: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: str | None = None,
    ) -> Reservation:
        reservation = Reservation(
            reservation_id=reservation_id,
            sku=sku,
            quantity=quantity,
            status=ReservationStatus.PENDING,
            expires_at=expires_at,
            created_at=datetime.utcnow(),
            idempotency_key=idempotency_key,
        )
        self.session.add(reservation)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise RepositoryError("Idempotency key conflict")
        return reservation

    def get_reservation(self, reservation_id: str) -> Reservation | None:
        return self.session.execute(
            select(Reservation).where(Reservation.reservation_id == reservation_id)
        ).scalar_one_or_none()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        return self.session.execute(
            select(Reservation).where(Reservation.idempotency_key == idempotency_key)
        ).scalar_one_or_none()

    def update_reservation_status(self, reservation_id: str, status: ReservationStatus):
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise RepositoryError(f"Reservation {reservation_id} not found")
        reservation.status = status
        self.session.commit()

    def create_order(self, order_id: str, sku: str, quantity: int, reservation_id: str) -> Order:
        order = Order(
            order_id=order_id,
            sku=sku,
            quantity=quantity,
            created_at=datetime.utcnow(),
            reservation_id=reservation_id,
        )
        self.session.add(order)
        self.session.commit()
        return order

    def get_order(self, order_id: str) -> Order | None:
        return self.session.execute(select(Order).where(Order.order_id == order_id)).scalar_one_or_none()

    def list_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[Order], int]:
        offset = (page - 1) * page_size
        stmt = select(Order).order_by(desc(Order.created_at)).offset(offset).limit(page_size)
        orders = self.session.execute(stmt).scalars().all()
        total = self.session.execute(select(Order)).scalars().all().__len__()
        return orders, total

    def get_pending_reservations_for_sku(self, sku: str) -> list[Reservation]:
        stmt = select(Reservation).where(
            (Reservation.sku == sku) & (Reservation.status == ReservationStatus.PENDING)
        )
        return self.session.execute(stmt).scalars().all()
