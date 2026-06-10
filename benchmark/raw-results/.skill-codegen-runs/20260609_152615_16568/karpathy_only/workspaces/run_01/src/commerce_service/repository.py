from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from .models import SKUModel, ReservationModel, OrderModel, ReservationStatus, OrderStatus


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # SKU Operations
    def get_sku(self, sku_id: str) -> Optional[SKUModel]:
        return self.session.query(SKUModel).filter(SKUModel.sku_id == sku_id).first()

    def create_sku(self, sku_id: str, quantity: int) -> SKUModel:
        sku = SKUModel(sku_id=sku_id, quantity=quantity)
        self.session.add(sku)
        self.session.commit()
        return sku

    def update_stock(self, sku_id: str, adjustment: int) -> SKUModel:
        sku = self.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        sku.quantity += adjustment
        self.session.commit()
        return sku

    # Reservation Operations
    def get_reservation(self, reservation_id: str) -> Optional[ReservationModel]:
        return (
            self.session.query(ReservationModel)
            .filter(ReservationModel.reservation_id == reservation_id)
            .first()
        )

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationModel]:
        return (
            self.session.query(ReservationModel)
            .filter(ReservationModel.idempotency_key == idempotency_key)
            .first()
        )

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> ReservationModel:
        reservation = ReservationModel(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def update_reservation_status(
        self, reservation_id: str, status: ReservationStatus
    ) -> ReservationModel:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.status = status
        self.session.commit()
        return reservation

    # Order Operations
    def get_order(self, order_id: str) -> Optional[OrderModel]:
        return self.session.query(OrderModel).filter(OrderModel.order_id == order_id).first()

    def create_order(
        self,
        order_id: str,
        reservation_id: str,
        sku_id: str,
        quantity: int,
    ) -> OrderModel:
        order = OrderModel(
            order_id=order_id,
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
        )
        self.session.add(order)
        self.session.commit()
        return order

    def list_orders(self, limit: int = 10, cursor: Optional[str] = None) -> tuple[list[OrderModel], Optional[str]]:
        import base64
        import json

        query = self.session.query(OrderModel).order_by(OrderModel.created_at.desc(), OrderModel.order_id.desc())

        if cursor:
            try:
                cursor_data = json.loads(base64.b64decode(cursor).decode())
                created_at_str = cursor_data["created_at"]
                order_id = cursor_data["order_id"]
                created_at = datetime.fromisoformat(created_at_str)

                query = query.filter(
                    (OrderModel.created_at < created_at) |
                    ((OrderModel.created_at == created_at) & (OrderModel.order_id < order_id))
                )
            except (ValueError, KeyError, TypeError):
                pass

        orders = query.limit(limit + 1).all()

        next_cursor = None
        if len(orders) > limit:
            last_returned = orders[limit - 1]
            next_cursor_data = {
                "created_at": last_returned.created_at.isoformat(),
                "order_id": last_returned.order_id,
            }
            next_cursor = base64.b64encode(json.dumps(next_cursor_data).encode()).decode()
            orders = orders[:limit]

        return orders, next_cursor

    def update_order_status(self, order_id: str, status: OrderStatus) -> OrderModel:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        order.status = status
        self.session.commit()
        return order
