from sqlalchemy.orm import Session

from . import models


class SKURepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, sku_id: str) -> models.SKU | None:
        return self.db.query(models.SKU).filter(models.SKU.id == sku_id).first()

    def create(self, sku_id: str, name: str, price: float) -> models.SKU:
        sku = models.SKU(id=sku_id, name=name, price=price)
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return sku


class StockRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, sku_id: str) -> models.Stock | None:
        return self.db.query(models.Stock).filter(models.Stock.sku_id == sku_id).first()

    def get_or_create(self, sku_id: str) -> models.Stock:
        stock = self.get(sku_id)
        if not stock:
            stock = models.Stock(sku_id=sku_id, quantity=0)
            self.db.add(stock)
            self.db.commit()
            self.db.refresh(stock)
        return stock

    def adjust(self, sku_id: str, quantity_delta: int) -> models.Stock:
        stock = self.get_or_create(sku_id)
        stock.quantity += quantity_delta
        self.db.commit()
        self.db.refresh(stock)
        return stock


class ReservationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, reservation_id: str) -> models.Reservation | None:
        return self.db.query(models.Reservation).filter(
            models.Reservation.id == reservation_id
        ).first()

    def get_by_idempotency_key(self, key: str) -> models.Reservation | None:
        return self.db.query(models.Reservation).filter(
            models.Reservation.idempotency_key == key
        ).first()

    def create(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        expires_at,
        order_id: str,
    ) -> models.Reservation:
        reservation = models.Reservation(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            order_id=order_id,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def update_status(self, reservation_id: str, status: models.ReservationStatus) -> models.Reservation:
        reservation = self.get(reservation_id)
        if reservation:
            reservation.status = status
            self.db.commit()
            self.db.refresh(reservation)
        return reservation


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, order_id: str) -> models.Order | None:
        return self.db.query(models.Order).filter(models.Order.id == order_id).first()

    def create(self, order_id: str) -> models.Order:
        order = models.Order(id=order_id, status=models.OrderStatus.RESERVED)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def list(self, limit: int, offset: int) -> tuple[list[models.Order], int]:
        query = self.db.query(models.Order)
        total = query.count()
        orders = query.offset(offset).limit(limit).all()
        return orders, total

    def update_status(self, order_id: str, status: models.OrderStatus) -> models.Order:
        order = self.get(order_id)
        if order:
            order.status = status
            self.db.commit()
            self.db.refresh(order)
        return order
