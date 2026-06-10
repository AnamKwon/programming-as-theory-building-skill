from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    OrderModel,
    OrderStatus,
    ReservationModel,
    ReservationStatus,
    SKUModel,
    StockModel,
)


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def get_sku(self, sku_code: str) -> SKUModel | None:
        return self.session.execute(
            select(SKUModel).where(SKUModel.sku_code == sku_code)
        ).scalar_one_or_none()

    def create_sku(self, sku_code: str, name: str, description: str | None) -> SKUModel:
        sku = SKUModel(sku_code=sku_code, name=name, description=description)
        self.session.add(sku)
        self.session.flush()
        return sku

    def get_stock(self, sku_code: str) -> StockModel | None:
        return self.session.execute(
            select(StockModel).where(StockModel.sku_code == sku_code)
        ).scalar_one_or_none()

    def create_stock(self, sku_code: str, available: int = 0) -> StockModel:
        stock = StockModel(sku_code=sku_code, available=available, reserved=0)
        self.session.add(stock)
        self.session.flush()
        return stock

    def update_stock_available(self, sku_code: str, delta: int) -> StockModel:
        stock = self.get_stock(sku_code)
        if not stock:
            raise ValueError(f"Stock not found for SKU: {sku_code}")
        stock.available += delta
        stock.updated_at = datetime.utcnow()
        self.session.flush()
        return stock

    def reserve_stock(self, sku_code: str, quantity: int) -> StockModel:
        stock = self.get_stock(sku_code)
        if not stock:
            raise ValueError(f"Stock not found for SKU: {sku_code}")
        if stock.available < quantity:
            raise ValueError("Insufficient stock available")
        stock.available -= quantity
        stock.reserved += quantity
        stock.updated_at = datetime.utcnow()
        self.session.flush()
        return stock

    def release_reserved_stock(self, sku_code: str, quantity: int) -> StockModel:
        stock = self.get_stock(sku_code)
        if not stock:
            raise ValueError(f"Stock not found for SKU: {sku_code}")
        stock.reserved -= quantity
        stock.available += quantity
        stock.updated_at = datetime.utcnow()
        self.session.flush()
        return stock

    def get_reservation(self, reservation_id: int) -> ReservationModel | None:
        return self.session.execute(
            select(ReservationModel).where(ReservationModel.id == reservation_id)
        ).scalar_one_or_none()

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> ReservationModel | None:
        return self.session.execute(
            select(ReservationModel).where(
                ReservationModel.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()

    def create_reservation(
        self,
        sku_code: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: str | None = None,
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku_code=sku_code,
            quantity=quantity,
            status=ReservationStatus.PENDING,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.session.add(reservation)
        self.session.flush()
        return reservation

    def update_reservation_status(
        self, reservation_id: int, status: ReservationStatus
    ) -> ReservationModel:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {reservation_id}")
        reservation.status = status
        self.session.flush()
        return reservation

    def get_order(self, order_id: int) -> OrderModel | None:
        return self.session.execute(
            select(OrderModel).where(OrderModel.id == order_id)
        ).scalar_one_or_none()

    def create_order(
        self,
        sku_code: str,
        quantity: int,
        reservation_id: int | None = None,
    ) -> OrderModel:
        order = OrderModel(
            sku_code=sku_code,
            quantity=quantity,
            status=OrderStatus.PENDING,
            reservation_id=reservation_id,
        )
        self.session.add(order)
        self.session.flush()
        return order

    def update_order_status(self, order_id: int, status: OrderStatus) -> OrderModel:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")
        order.status = status
        order.updated_at = datetime.utcnow()
        self.session.flush()
        return order

    def list_orders(self, offset: int = 0, limit: int = 20) -> tuple[list[OrderModel], int]:
        from sqlalchemy import func
        query = select(OrderModel)
        total = self.session.execute(select(func.count()).select_from(OrderModel)).scalar() or 0
        orders = self.session.execute(
            query.offset(offset).limit(limit)
        ).scalars().all()
        return orders, total

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()
