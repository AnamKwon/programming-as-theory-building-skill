from datetime import datetime

from sqlalchemy import and_
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
    def __init__(self, db: Session):
        self.db = db

    # SKU Operations
    def create_sku(self, sku: str, name: str, base_price: float) -> SKUModel:
        model = SKUModel(sku=sku, name=name, base_price=base_price)
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def get_sku(self, sku_id: int) -> SKUModel | None:
        return self.db.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def get_sku_by_code(self, sku: str) -> SKUModel | None:
        return self.db.query(SKUModel).filter(SKUModel.sku == sku).first()

    # Stock Operations
    def get_or_create_stock(self, sku_id: int) -> StockModel:
        stock = self.db.query(StockModel).filter(StockModel.sku_id == sku_id).first()
        if not stock:
            stock = StockModel(sku_id=sku_id, quantity=0)
            self.db.add(stock)
            self.db.commit()
            self.db.refresh(stock)
        return stock

    def adjust_stock(self, sku_id: int, quantity_delta: int) -> StockModel:
        stock = self.get_or_create_stock(sku_id)
        stock.quantity += quantity_delta
        self.db.commit()
        self.db.refresh(stock)
        return stock

    def get_stock(self, sku_id: int) -> StockModel | None:
        return self.db.query(StockModel).filter(StockModel.sku_id == sku_id).first()

    # Reservation Operations
    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        expires_at: datetime,
        idempotency_key: str | None = None,
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku_id=sku_id,
            quantity=quantity,
            status=ReservationStatus.PENDING,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> ReservationModel | None:
        return (
            self.db.query(ReservationModel)
            .filter(ReservationModel.id == reservation_id)
            .first()
        )

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> ReservationModel | None:
        return (
            self.db.query(ReservationModel)
            .filter(ReservationModel.idempotency_key == idempotency_key)
            .first()
        )

    def update_reservation_status(
        self, reservation_id: int, status: ReservationStatus
    ) -> ReservationModel:
        reservation = self.get_reservation(reservation_id)
        if reservation:
            reservation.status = status
            self.db.commit()
            self.db.refresh(reservation)
        return reservation

    def get_pending_reservations_by_sku(self, sku_id: int) -> list[ReservationModel]:
        return (
            self.db.query(ReservationModel)
            .filter(
                and_(
                    ReservationModel.sku_id == sku_id,
                    ReservationModel.status == ReservationStatus.PENDING,
                )
            )
            .all()
        )

    # Order Operations
    def create_order(
        self, reservation_id: int, quantity_reserved: int
    ) -> OrderModel:
        order = OrderModel(
            reservation_id=reservation_id,
            status=OrderStatus.PENDING,
            quantity_reserved=quantity_reserved,
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_order(self, order_id: int) -> OrderModel | None:
        return self.db.query(OrderModel).filter(OrderModel.id == order_id).first()

    def get_order_by_reservation(self, reservation_id: int) -> OrderModel | None:
        return (
            self.db.query(OrderModel)
            .filter(OrderModel.reservation_id == reservation_id)
            .first()
        )

    def update_order_status(
        self, order_id: int, status: OrderStatus
    ) -> OrderModel:
        order = self.get_order(order_id)
        if order:
            order.status = status
            self.db.commit()
            self.db.refresh(order)
        return order

    def list_orders(
        self, page: int = 1, page_size: int = 10
    ) -> tuple[list[OrderModel], int]:
        query = self.db.query(OrderModel)
        total = query.count()
        offset = (page - 1) * page_size
        orders = query.offset(offset).limit(page_size).all()
        return orders, total

    def get_total_reserved_for_sku(
        self, sku_id: int, exclude_statuses: list[str] | None = None
    ) -> int:
        query = self.db.query(ReservationModel).filter(
            ReservationModel.sku_id == sku_id
        )
        if exclude_statuses:
            query = query.filter(~ReservationModel.status.in_(exclude_statuses))
        else:
            query = query.filter(ReservationModel.status == ReservationStatus.PENDING)
        result = query.with_entities(func_sum(ReservationModel.quantity)).scalar()
        return result or 0


# Import after class definition to avoid circular import
from sqlalchemy import func as func_sum
