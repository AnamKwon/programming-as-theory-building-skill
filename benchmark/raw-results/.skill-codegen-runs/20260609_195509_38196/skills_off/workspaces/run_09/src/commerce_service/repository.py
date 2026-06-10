from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .models import OrderModel, OrderStatus, ReservationModel, ReservationStatus, SKUModel


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku_code: str, initial_stock: int) -> SKUModel:
        sku = SKUModel(sku_code=sku_code, current_stock=initial_stock, reserved_count=0)
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def get_sku(self, sku_id: int) -> SKUModel | None:
        return self.db.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def get_sku_by_code(self, sku_code: str) -> SKUModel | None:
        return self.db.query(SKUModel).filter(SKUModel.sku_code == sku_code).first()

    def update_sku_stock(self, sku_id: int, current_stock: int, reserved_count: int) -> SKUModel:
        sku = self.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        sku.current_stock = current_stock
        sku.reserved_count = reserved_count
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str, expires_at: datetime
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status=ReservationStatus.PENDING,
            expires_at=expires_at,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> ReservationModel | None:
        return self.db.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> ReservationModel | None:
        return (
            self.db.query(ReservationModel)
            .filter(ReservationModel.idempotency_key == idempotency_key)
            .first()
        )

    def update_reservation_status(self, reservation_id: int, status: ReservationStatus) -> ReservationModel:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.status = status
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def create_order(
        self, sku_id: int, quantity: int, reservation_id: int | None = None
    ) -> OrderModel:
        order = OrderModel(
            sku_id=sku_id, quantity=quantity, status=OrderStatus.PENDING, reservation_id=reservation_id
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_order(self, order_id: int) -> OrderModel | None:
        return self.db.query(OrderModel).filter(OrderModel.id == order_id).first()

    def update_order_status(self, order_id: int, status: OrderStatus) -> OrderModel:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        order.status = status
        self.db.commit()
        self.db.refresh(order)
        return order

    def list_orders(self, skip: int = 0, limit: int = 10) -> tuple[list[OrderModel], int]:
        query = self.db.query(OrderModel)
        total = query.count()
        orders = query.offset(skip).limit(limit).all()
        return orders, total

    def get_pending_expired_reservations(self) -> list[ReservationModel]:
        now = datetime.now(timezone.utc)
        return (
            self.db.query(ReservationModel)
            .filter(
                ReservationModel.status == ReservationStatus.PENDING,
                ReservationModel.expires_at < now,
            )
            .all()
        )
