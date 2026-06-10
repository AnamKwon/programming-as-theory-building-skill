from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import SKU, Reservation, Order, ReservationStatus, OrderStatus


class Repository:
    """Data access layer for SKUs, Reservations, and Orders."""

    def __init__(self, session: Session):
        self.session = session

    # ─── SKU Operations ──────────────────────────────────────────────────────

    def create_sku(self, name: str, initial_stock: int) -> SKU:
        sku = SKU(name=name, stock_level=initial_stock)
        self.session.add(sku)
        self.session.commit()
        return sku

    def get_sku(self, sku_id: int) -> Optional[SKU]:
        return self.session.query(SKU).filter(SKU.id == sku_id).first()

    def adjust_stock(self, sku_id: int, adjustment: int) -> SKU:
        sku = self.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        sku.stock_level += adjustment
        self.session.commit()
        return sku

    # ─── Reservation Operations ──────────────────────────────────────────────

    def get_reservation(self, reservation_id: int) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[Reservation]:
        return (
            self.session.query(Reservation)
            .filter(Reservation.idempotency_key == key)
            .first()
        )

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> Reservation:
        reservation = Reservation(
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def mark_reservation_confirmed(self, reservation_id: int) -> Reservation:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.status = ReservationStatus.CONFIRMED
        self.session.commit()
        return reservation

    def mark_reservation_cancelled(self, reservation_id: int) -> Reservation:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.status = ReservationStatus.CANCELLED
        self.session.commit()
        return reservation

    def mark_reservation_expired(self, reservation_id: int) -> Reservation:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.status = ReservationStatus.EXPIRED
        self.session.commit()
        return reservation

    # ─── Order Operations ────────────────────────────────────────────────────

    def create_order(self, reservation_id: int, sku_id: int, quantity: int) -> Order:
        order = Order(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
        )
        self.session.add(order)
        self.session.commit()
        return order

    def get_order(self, order_id: int) -> Optional[Order]:
        return self.session.query(Order).filter(Order.id == order_id).first()

    def list_orders(self, skip: int = 0, limit: int = 20) -> tuple[list[Order], int]:
        total = self.session.query(Order).count()
        orders = (
            self.session.query(Order)
            .order_by(Order.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return orders, total
