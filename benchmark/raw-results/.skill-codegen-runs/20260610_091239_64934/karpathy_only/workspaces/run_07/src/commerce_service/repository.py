from typing import Optional

from sqlalchemy.orm import Session

from .models import Order, OrderStatus, Reservation, ReservationStatus, SKU, SKUStatus


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, code: str, quantity_available: int) -> SKU:
        sku = SKU(code=code, quantity_available=quantity_available, status=SKUStatus.ACTIVE.value)
        self.session.add(sku)
        self.session.commit()
        self.session.refresh(sku)
        return sku

    def get_sku(self, sku_id: int) -> Optional[SKU]:
        return self.session.query(SKU).filter(SKU.id == sku_id).first()

    def get_sku_by_code(self, code: str) -> Optional[SKU]:
        return self.session.query(SKU).filter(SKU.code == code).first()

    def update_sku_stock(self, sku_id: int, adjustment: int) -> Optional[SKU]:
        sku = self.get_sku(sku_id)
        if not sku:
            return None
        sku.quantity_available = max(0, sku.quantity_available + adjustment)
        self.session.commit()
        self.session.refresh(sku)
        return sku

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str, expires_at
    ) -> Reservation:
        reservation = Reservation(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status=ReservationStatus.PENDING.value,
            expires_at=expires_at,
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[Reservation]:
        return (
            self.session.query(Reservation)
            .filter(Reservation.idempotency_key == idempotency_key)
            .first()
        )

    def update_reservation_status(self, reservation_id: int, status: str) -> Optional[Reservation]:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def create_order(
        self, sku_id: int, quantity: int, reservation_id: Optional[int] = None
    ) -> Order:
        order = Order(
            sku_id=sku_id,
            quantity=quantity,
            status=OrderStatus.PENDING.value,
            reservation_id=reservation_id,
        )
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_order(self, order_id: int) -> Optional[Order]:
        return self.session.query(Order).filter(Order.id == order_id).first()

    def get_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[Order], int]:
        query = self.session.query(Order)
        total = query.count()
        offset = (page - 1) * page_size
        orders = query.offset(offset).limit(page_size).all()
        return orders, total

    def get_pending_reservations_for_sku(self, sku_id: int) -> list[Reservation]:
        return (
            self.session.query(Reservation)
            .filter(
                Reservation.sku_id == sku_id,
                Reservation.status == ReservationStatus.PENDING.value,
            )
            .all()
        )

    def get_confirmed_orders_for_sku(self, sku_id: int) -> list[Order]:
        return (
            self.session.query(Order)
            .filter(
                Order.sku_id == sku_id,
                Order.status == OrderStatus.FULFILLED.value,
            )
            .all()
        )
