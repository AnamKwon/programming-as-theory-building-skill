from sqlalchemy.orm import Session
from sqlalchemy import desc
from .models import SKU, Reservation, Order

class Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        """Create a new SKU with initial stock."""
        sku_obj = SKU(sku=sku, available_stock=initial_stock)
        self.db.add(sku_obj)
        self.db.commit()
        self.db.refresh(sku_obj)
        return sku_obj

    def get_sku_by_code(self, sku: str) -> SKU | None:
        """Get SKU by SKU code."""
        return self.db.query(SKU).filter(SKU.sku == sku).first()

    def adjust_stock(self, sku: str, amount: int) -> SKU:
        """Adjust stock level for a SKU."""
        sku_obj = self.get_sku_by_code(sku)
        if sku_obj:
            sku_obj.available_stock += amount
            self.db.commit()
            self.db.refresh(sku_obj)
        return sku_obj

    def get_reservation_by_idempotency_key(self, key: str) -> Reservation | None:
        """Get reservation by idempotency key."""
        return self.db.query(Reservation).filter(Reservation.idempotency_key == key).first()

    def create_reservation(self, sku_id: int, quantity: int, idempotency_key: str) -> Reservation:
        """Create a new reservation."""
        reservation = Reservation(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status="PENDING"
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> Reservation | None:
        """Get reservation by ID."""
        return self.db.query(Reservation).filter(Reservation.id == reservation_id).first()

    def update_reservation_status(self, reservation_id: int, status: str) -> Reservation | None:
        """Update reservation status."""
        reservation = self.get_reservation(reservation_id)
        if reservation:
            reservation.status = status
            self.db.commit()
            self.db.refresh(reservation)
        return reservation

    def deduct_stock(self, sku_id: int, quantity: int):
        """Deduct stock from a SKU."""
        sku = self.db.query(SKU).filter(SKU.id == sku_id).first()
        if sku:
            sku.available_stock -= quantity
            self.db.commit()

    def restore_stock(self, sku_id: int, quantity: int):
        """Restore stock to a SKU."""
        sku = self.db.query(SKU).filter(SKU.id == sku_id).first()
        if sku:
            sku.available_stock += quantity
            self.db.commit()

    def create_order(self, reservation_id: int) -> Order:
        """Create an order from a reservation."""
        order = Order(reservation_id=reservation_id)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def list_orders(self, page: int, size: int) -> tuple[list[Order], int]:
        """List orders with pagination."""
        total = self.db.query(Order).count()
        offset = (page - 1) * size
        orders = self.db.query(Order).order_by(desc(Order.created_at)).offset(offset).limit(size).all()
        return orders, total
