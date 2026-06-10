from datetime import datetime
from typing import Optional

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from .models import OrderRow, ReservationRow, ReservationStatus, SKURow, StockRow


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, code: str, description: str) -> SKURow:
        sku = SKURow(code=code, description=description)
        self.session.add(sku)
        self.session.commit()
        return sku

    def get_sku(self, sku_id: str) -> Optional[SKURow]:
        return self.session.query(SKURow).filter(SKURow.id == sku_id).first()

    def get_sku_by_code(self, code: str) -> Optional[SKURow]:
        return self.session.query(SKURow).filter(SKURow.code == code).first()

    def get_stock(self, sku_id: str) -> Optional[StockRow]:
        return self.session.query(StockRow).filter(StockRow.sku_id == sku_id).first()

    def initialize_stock(self, sku_id: str, quantity: int = 0) -> StockRow:
        stock = StockRow(sku_id=sku_id, quantity=quantity)
        self.session.add(stock)
        self.session.commit()
        return stock

    def adjust_stock(self, sku_id: str, adjustment: int) -> Optional[StockRow]:
        stock = self.get_stock(sku_id)
        if not stock:
            return None
        stock.quantity += adjustment
        stock.updated_at = datetime.utcnow()
        self.session.commit()
        return stock

    def create_reservation(
        self,
        sku_id: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> ReservationRow:
        reservation = ReservationRow(
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
            status=ReservationStatus.PENDING.value,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get_reservation(self, reservation_id: str) -> Optional[ReservationRow]:
        return (
            self.session.query(ReservationRow)
            .filter(ReservationRow.id == reservation_id)
            .first()
        )

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[ReservationRow]:
        return (
            self.session.query(ReservationRow)
            .filter(ReservationRow.idempotency_key == idempotency_key)
            .first()
        )

    def update_reservation_status(
        self, reservation_id: str, status: str
    ) -> Optional[ReservationRow]:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.session.commit()
        return reservation

    def create_order(
        self, sku_id: str, quantity: int, reservation_id: str
    ) -> OrderRow:
        order = OrderRow(sku_id=sku_id, quantity=quantity, reservation_id=reservation_id)
        self.session.add(order)
        self.session.commit()
        return order

    def get_order(self, order_id: str) -> Optional[OrderRow]:
        return self.session.query(OrderRow).filter(OrderRow.id == order_id).first()

    def list_orders(
        self, offset: int = 0, limit: int = 10
    ) -> tuple[list[OrderRow], int]:
        query = self.session.query(OrderRow)
        total = query.count()
        orders = query.order_by(desc(OrderRow.created_at)).offset(offset).limit(limit).all()
        return orders, total
