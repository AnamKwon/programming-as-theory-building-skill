from sqlalchemy.orm import Session
from .models import SKUModel, ReservationModel, OrderModel
from datetime import datetime


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> SKUModel:
        sku_record = SKUModel(sku=sku, stock=initial_stock)
        self.db.add(sku_record)
        self.db.commit()
        self.db.refresh(sku_record)
        return sku_record

    def get_sku_by_name(self, sku: str) -> SKUModel | None:
        return self.db.query(SKUModel).filter(SKUModel.sku == sku).first()

    def adjust_stock(self, sku: str, amount: int) -> SKUModel:
        sku_record = self.get_sku_by_name(sku)
        if not sku_record:
            raise ValueError(f"SKU {sku} not found")
        sku_record.stock += amount
        self.db.commit()
        self.db.refresh(sku_record)
        return sku_record

    def get_reservation_by_idempotency_key(self, key: str) -> ReservationModel | None:
        return self.db.query(ReservationModel).filter(
            ReservationModel.idempotency_key == key
        ).first()

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> ReservationModel:
        sku_record = self.get_sku_by_name(sku)
        if not sku_record:
            raise ValueError(f"SKU {sku} not found")

        reservation = ReservationModel(
            sku=sku,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status="PENDING",
            sku_id=sku_record.id,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> ReservationModel | None:
        return self.db.query(ReservationModel).filter(
            ReservationModel.id == reservation_id
        ).first()

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> ReservationModel:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.status = status
        if status == "CONFIRMED":
            reservation.confirmed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def create_order(self, reservation_id: int) -> OrderModel:
        order = OrderModel(reservation_id=reservation_id)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[OrderModel], int]:
        query = self.db.query(OrderModel)
        total = query.count()
        offset = (page - 1) * size
        orders = query.offset(offset).limit(size).all()
        return orders, total
