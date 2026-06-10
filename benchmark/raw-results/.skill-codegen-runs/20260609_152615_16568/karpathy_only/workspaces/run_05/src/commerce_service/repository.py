from datetime import datetime

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from .models import Order, OrderStatus, Reservation, SKU


class Repository:
    def __init__(self, db: Session):
        self.db = db

    # === SKU Operations ===

    def get_sku(self, sku_id: str) -> SKU | None:
        return self.db.query(SKU).filter(SKU.id == sku_id).first()

    def create_sku(self, sku_id: str, initial_stock: int) -> SKU:
        sku = SKU(id=sku_id, available_stock=initial_stock)
        self.db.add(sku)
        self.db.commit()
        return sku

    def update_stock(self, sku_id: str, delta: int) -> SKU | None:
        sku = self.get_sku(sku_id)
        if not sku:
            return None
        sku.available_stock += delta
        self.db.commit()
        return sku

    # === Reservation Operations ===

    def get_reservation(self, reservation_id: str) -> Reservation | None:
        return self.db.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        return self.db.query(Reservation).filter(
            Reservation.idempotency_key == idempotency_key
        ).first()

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> Reservation:
        reservation = Reservation(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status=OrderStatus.PENDING_RESERVATION,
            expires_at=expires_at,
        )
        self.db.add(reservation)
        self.db.commit()
        return reservation

    def update_reservation_status(
        self, reservation_id: str, status: OrderStatus
    ) -> Reservation | None:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.db.commit()
        return reservation

    def delete_reservation(self, reservation_id: str) -> bool:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return False
        self.db.delete(reservation)
        self.db.commit()
        return True

    # === Order Operations ===

    def get_order(self, order_id: str) -> Order | None:
        return self.db.query(Order).filter(Order.id == order_id).first()

    def create_order(
        self,
        order_id: str,
        sku_id: str,
        quantity: int,
        reservation_id: str | None = None,
    ) -> Order:
        order = Order(
            id=order_id,
            sku_id=sku_id,
            quantity=quantity,
            reservation_id=reservation_id,
            status=OrderStatus.CONFIRMED,
        )
        self.db.add(order)
        self.db.commit()
        return order

    def list_orders(self, limit: int, offset: int) -> tuple[list[Order], int]:
        total = self.db.query(func.count(Order.id)).scalar() or 0
        orders = (
            self.db.query(Order)
            .order_by(Order.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return orders, total

    # === Utility ===

    def count_active_reservations(self, sku_id: str) -> int:
        now = datetime.utcnow()
        return (
            self.db.query(func.count(Reservation.id))
            .filter(
                and_(
                    Reservation.sku_id == sku_id,
                    Reservation.status == OrderStatus.RESERVED,
                    Reservation.expires_at > now,
                )
            )
            .scalar()
            or 0
        )

    def sum_reserved_quantity(self, sku_id: str) -> int:
        now = datetime.utcnow()
        result = (
            self.db.query(func.sum(Reservation.quantity))
            .filter(
                and_(
                    Reservation.sku_id == sku_id,
                    Reservation.status == OrderStatus.RESERVED,
                    Reservation.expires_at > now,
                )
            )
            .scalar()
        )
        return result or 0
