from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc
from commerce_service.models import SKU, Reservation, Order


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        sku_record = SKU(sku=sku, available_stock=initial_stock, reserved_stock=0)
        self.session.add(sku_record)
        self.session.commit()
        self.session.refresh(sku_record)
        return sku_record

    def get_sku_by_name(self, sku: str) -> Optional[SKU]:
        return self.session.query(SKU).filter(SKU.sku == sku).first()

    def adjust_stock(self, sku_id: int, amount: int) -> SKU:
        sku_record = self.session.query(SKU).filter(SKU.id == sku_id).first()
        if sku_record:
            sku_record.available_stock += amount
            self.session.commit()
            self.session.refresh(sku_record)
        return sku_record

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(
            Reservation.idempotency_key == idempotency_key
        ).first()

    def create_reservation(
        self,
        sku_id: int,
        sku: str,
        quantity: int,
        idempotency_key: str,
    ) -> Reservation:
        reservation = Reservation(
            sku_id=sku_id,
            sku=sku,
            quantity=quantity,
            status="PENDING",
            idempotency_key=idempotency_key,
            created_at=datetime.utcnow(),
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_reservation_by_id(self, reservation_id: int) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(Reservation.id == reservation_id).first()

    def update_reservation_status(self, reservation_id: int, status: str) -> Reservation:
        reservation = self.session.query(Reservation).filter(
            Reservation.id == reservation_id
        ).first()
        if reservation:
            reservation.status = status
            if status == "CONFIRMED":
                reservation.confirmed_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(reservation)
        return reservation

    def reserve_stock(self, sku_id: int, quantity: int) -> SKU:
        sku_record = self.session.query(SKU).filter(SKU.id == sku_id).first()
        if sku_record:
            sku_record.available_stock -= quantity
            sku_record.reserved_stock += quantity
            self.session.commit()
            self.session.refresh(sku_record)
        return sku_record

    def restore_stock(self, sku_id: int, quantity: int) -> SKU:
        sku_record = self.session.query(SKU).filter(SKU.id == sku_id).first()
        if sku_record:
            sku_record.available_stock += quantity
            sku_record.reserved_stock -= quantity
            self.session.commit()
            self.session.refresh(sku_record)
        return sku_record

    def create_order(self, reservation_id: int) -> Order:
        order = Order(reservation_id=reservation_id, created_at=datetime.utcnow())
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[List[Order], int]:
        skip = (page - 1) * size
        query = self.session.query(Order).order_by(desc(Order.created_at))
        total = query.count()
        orders = query.offset(skip).limit(size).all()
        return orders, total

    def get_order_by_reservation_id(self, reservation_id: int) -> Optional[Order]:
        return self.session.query(Order).filter(Order.reservation_id == reservation_id).first()
