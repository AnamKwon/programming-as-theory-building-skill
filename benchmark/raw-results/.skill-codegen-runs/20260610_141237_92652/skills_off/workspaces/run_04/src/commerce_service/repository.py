from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import Order, Reservation, SKU


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        db_sku = SKU(sku=sku, stock_level=initial_stock)
        self.db.add(db_sku)
        self.db.commit()
        self.db.refresh(db_sku)
        return db_sku

    def get_sku_by_code(self, sku: str) -> Optional[SKU]:
        return self.db.query(SKU).filter(SKU.sku == sku).first()

    def get_sku_by_id(self, sku_id: int) -> Optional[SKU]:
        return self.db.query(SKU).filter(SKU.id == sku_id).first()

    def update_sku_stock(self, sku_id: int, new_stock: int) -> SKU:
        sku = self.db.query(SKU).filter(SKU.id == sku_id).first()
        if sku:
            sku.stock_level = new_stock
            self.db.commit()
            self.db.refresh(sku)
        return sku

    def create_reservation(
        self,
        sku_id: int,
        sku_code: str,
        quantity: int,
        status: str,
        created_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> Reservation:
        reservation = Reservation(
            sku_id=sku_id,
            sku_code=sku_code,
            quantity=quantity,
            status=status,
            created_at=created_at,
            idempotency_key=idempotency_key,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation_by_id(self, reservation_id: int) -> Optional[Reservation]:
        return self.db.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[Reservation]:
        return (
            self.db.query(Reservation)
            .filter(Reservation.idempotency_key == idempotency_key)
            .first()
        )

    def update_reservation_status(self, reservation_id: int, status: str) -> Optional[Reservation]:
        reservation = self.db.query(Reservation).filter(Reservation.id == reservation_id).first()
        if reservation:
            reservation.status = status
            self.db.commit()
            self.db.refresh(reservation)
        return reservation

    def create_order(self, reservation_id: int, created_at: datetime) -> Order:
        order = Order(reservation_id=reservation_id, created_at=created_at)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_orders(self, offset: int = 0, limit: int = 10) -> tuple[list[Order], int]:
        total = self.db.query(Order).count()
        orders = self.db.query(Order).offset(offset).limit(limit).all()
        return orders, total
