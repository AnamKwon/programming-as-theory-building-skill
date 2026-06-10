from datetime import datetime

from sqlalchemy.orm import Session

from .models import Order, OrderStatus, Reservation, ReservationStatus, SKU


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # SKU operations
    def create_sku(self, sku_code: str, name: str, description: str | None, stock_level: int) -> SKU:
        sku = SKU(sku_code=sku_code, name=name, description=description, stock_level=stock_level)
        self.session.add(sku)
        self.session.commit()
        self.session.refresh(sku)
        return sku

    def get_sku(self, sku_id: int) -> SKU | None:
        return self.session.query(SKU).filter(SKU.id == sku_id).first()

    def get_sku_by_code(self, sku_code: str) -> SKU | None:
        return self.session.query(SKU).filter(SKU.sku_code == sku_code).first()

    def adjust_stock(self, sku_id: int, quantity_change: int) -> SKU:
        sku = self.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        sku.stock_level += quantity_change
        self.session.commit()
        self.session.refresh(sku)
        return sku

    # Reservation operations
    def create_reservation(
        self,
        order_id: str,
        sku_id: int,
        quantity: int,
        expires_at: datetime,
        idempotency_key: str,
    ) -> Reservation:
        reservation = Reservation(
            order_id=order_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
            status=ReservationStatus.PENDING,
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> Reservation | None:
        return self.session.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        return self.session.query(Reservation).filter(Reservation.idempotency_key == idempotency_key).first()

    def confirm_reservation(self, reservation_id: int) -> Reservation:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.status = ReservationStatus.CONFIRMED
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def cancel_reservation(self, reservation_id: int) -> Reservation:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.status = ReservationStatus.CANCELLED
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def expire_reservation(self, reservation_id: int) -> Reservation:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.status = ReservationStatus.EXPIRED
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_reservations_by_order(self, order_id: str) -> list[Reservation]:
        return self.session.query(Reservation).filter(Reservation.order_id == order_id).all()

    # Order operations
    def create_order(self, order_id: str, total_items: int) -> Order:
        order = Order(id=order_id, total_items=total_items, status=OrderStatus.RESERVED)
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_order(self, order_id: str) -> Order | None:
        return self.session.query(Order).filter(Order.id == order_id).first()

    def confirm_order(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        order.status = OrderStatus.CONFIRMED
        order.confirmed_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(order)
        return order

    def cancel_order(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        order.status = OrderStatus.CANCELLED
        self.session.commit()
        self.session.refresh(order)
        return order

    def list_orders(self, limit: int = 20, offset: int = 0) -> tuple[list[Order], int]:
        query = self.session.query(Order).order_by(Order.created_at.desc())
        total = query.count()
        orders = query.limit(limit).offset(offset).all()
        return orders, total
