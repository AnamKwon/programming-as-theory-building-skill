from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_

from .models import SKUModel, StockModel, ReservationModel, OrderModel


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku_id: str, name: str, price: float) -> SKUModel:
        sku = SKUModel(id=sku_id, name=name, price=price)
        stock = StockModel(sku_id=sku_id, quantity_available=0, quantity_reserved=0)
        self.db.add(sku)
        self.db.add(stock)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def get_sku(self, sku_id: str) -> Optional[SKUModel]:
        return self.db.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def get_stock(self, sku_id: str) -> Optional[StockModel]:
        return self.db.query(StockModel).filter(StockModel.sku_id == sku_id).first()

    def adjust_stock(self, sku_id: str, quantity_change: int) -> StockModel:
        stock = self.get_stock(sku_id)
        if not stock:
            raise ValueError(f"Stock not found for SKU {sku_id}")

        new_quantity = stock.quantity_available + quantity_change
        if new_quantity < 0:
            raise ValueError("Quantity cannot be negative")

        stock.quantity_available = new_quantity
        stock.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(stock)
        return stock

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> ReservationModel:
        reservation = ReservationModel(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status="pending",
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: str) -> Optional[ReservationModel]:
        return self.db.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationModel]:
        return self.db.query(ReservationModel).filter(
            ReservationModel.idempotency_key == idempotency_key
        ).first()

    def update_reservation_status(self, reservation_id: str, status: str) -> ReservationModel:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        reservation.status = status
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def reserve_stock(self, sku_id: str, quantity: int) -> bool:
        stock = self.get_stock(sku_id)
        if not stock:
            return False

        if stock.quantity_available >= quantity:
            stock.quantity_available -= quantity
            stock.quantity_reserved += quantity
            stock.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(stock)
            return True
        return False

    def release_reservation(self, sku_id: str, quantity: int) -> StockModel:
        stock = self.get_stock(sku_id)
        if not stock:
            raise ValueError(f"Stock not found for SKU {sku_id}")

        stock.quantity_reserved -= quantity
        stock.quantity_available += quantity
        stock.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(stock)
        return stock

    def confirm_reservation(self, sku_id: str, quantity: int) -> StockModel:
        stock = self.get_stock(sku_id)
        if not stock:
            raise ValueError(f"Stock not found for SKU {sku_id}")

        stock.quantity_reserved -= quantity
        stock.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(stock)
        return stock

    def create_order(self, order_id: str) -> OrderModel:
        order = OrderModel(id=order_id, status="pending")
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_order(self, order_id: str) -> Optional[OrderModel]:
        return self.db.query(OrderModel).filter(OrderModel.id == order_id).first()

    def list_orders(self, skip: int = 0, limit: int = 10) -> Tuple[list[OrderModel], int]:
        total = self.db.query(OrderModel).count()
        orders = self.db.query(OrderModel).offset(skip).limit(limit).all()
        return orders, total

    def update_order_status(self, order_id: str, status: str) -> OrderModel:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        order.status = status
        order.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_active_reservations(self, sku_id: str) -> list[ReservationModel]:
        now = datetime.utcnow()
        return self.db.query(ReservationModel).filter(
            and_(
                ReservationModel.sku_id == sku_id,
                ReservationModel.status.in_(["pending", "confirmed"]),
                ReservationModel.expires_at > now,
            )
        ).all()

    def get_expired_reservations(self) -> list[ReservationModel]:
        now = datetime.utcnow()
        return self.db.query(ReservationModel).filter(
            and_(
                ReservationModel.status == "pending",
                ReservationModel.expires_at <= now,
            )
        ).all()
