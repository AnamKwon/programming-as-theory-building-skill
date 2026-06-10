from sqlalchemy.orm import Session
from .models import SKU, Reservation, Order


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        db_sku = SKU(sku=sku, available_stock=initial_stock)
        self.db.add(db_sku)
        self.db.commit()
        self.db.refresh(db_sku)
        return db_sku

    def get_sku(self, sku: str) -> SKU:
        return self.db.query(SKU).filter(SKU.sku == sku).first()

    def adjust_stock(self, sku: str, amount: int) -> SKU:
        db_sku = self.get_sku(sku)
        if db_sku:
            db_sku.available_stock += amount
            self.db.commit()
            self.db.refresh(db_sku)
        return db_sku

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Reservation:
        db_reservation = Reservation(
            sku=sku, quantity=quantity, idempotency_key=idempotency_key, status="PENDING"
        )
        self.db.add(db_reservation)
        self.db.commit()
        self.db.refresh(db_reservation)
        return db_reservation

    def get_reservation(self, reservation_id: int) -> Reservation:
        return self.db.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, key: str) -> Reservation:
        return (
            self.db.query(Reservation)
            .filter(Reservation.idempotency_key == key)
            .first()
        )

    def update_reservation_status(self, reservation_id: int, status: str) -> Reservation:
        db_reservation = self.get_reservation(reservation_id)
        if db_reservation:
            db_reservation.status = status
            self.db.commit()
            self.db.refresh(db_reservation)
        return db_reservation

    def create_order(self, reservation_id: int, sku: str, quantity: int) -> Order:
        db_order = Order(reservation_id=reservation_id, sku=sku, quantity=quantity)
        self.db.add(db_order)
        self.db.commit()
        self.db.refresh(db_order)
        return db_order

    def get_orders(self, page: int = 1, size: int = 10):
        skip = (page - 1) * size
        orders = self.db.query(Order).offset(skip).limit(size).all()
        total = self.db.query(Order).count()
        return orders, total
