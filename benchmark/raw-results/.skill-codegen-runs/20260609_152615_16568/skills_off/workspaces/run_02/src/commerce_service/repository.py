from typing import Optional

from sqlalchemy.orm import Session

from commerce_service.models import (
    Inventory,
    Order,
    OrderStatus,
    Reservation,
    ReservationStatus,
    SKU,
)


class Repository:
    def __init__(self, db: Session):
        self.db = db

    # SKU operations
    def create_sku(self, sku_id: str, name: str, price: float) -> SKU:
        sku = SKU(id=sku_id, name=name, price=price)
        self.db.add(sku)
        self.db.flush()
        return sku

    def get_sku(self, sku_id: str) -> Optional[SKU]:
        return self.db.query(SKU).filter(SKU.id == sku_id).first()

    def list_skus(self) -> list[SKU]:
        return self.db.query(SKU).all()

    # Inventory operations
    def get_inventory(self, sku_id: str) -> Optional[Inventory]:
        return self.db.query(Inventory).filter(Inventory.sku_id == sku_id).first()

    def create_inventory(self, sku_id: str, available: int = 0) -> Inventory:
        inventory = Inventory(sku_id=sku_id, available=available)
        self.db.add(inventory)
        self.db.flush()
        return inventory

    def adjust_inventory(self, sku_id: str, quantity_change: int) -> Optional[Inventory]:
        inventory = self.get_inventory(sku_id)
        if not inventory:
            return None
        inventory.available += quantity_change
        self.db.flush()
        return inventory

    def reserve_inventory(self, sku_id: str, quantity: int) -> bool:
        inventory = self.get_inventory(sku_id)
        if not inventory or inventory.available < quantity:
            return False
        inventory.available -= quantity
        inventory.reserved += quantity
        self.db.flush()
        return True

    def release_inventory(self, sku_id: str, quantity: int) -> Optional[Inventory]:
        inventory = self.get_inventory(sku_id)
        if not inventory:
            return None
        inventory.reserved -= quantity
        inventory.available += quantity
        self.db.flush()
        return inventory

    def confirm_inventory(self, sku_id: str, quantity: int) -> Optional[Inventory]:
        inventory = self.get_inventory(sku_id)
        if not inventory or inventory.reserved < quantity:
            return None
        inventory.reserved -= quantity
        self.db.flush()
        return inventory

    # Reservation operations
    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at,
        idempotency_key: Optional[str] = None,
    ) -> Reservation:
        reservation = Reservation(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.db.add(reservation)
        self.db.flush()
        return reservation

    def get_reservation(self, reservation_id: str) -> Optional[Reservation]:
        return self.db.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[Reservation]:
        return self.db.query(Reservation).filter(Reservation.idempotency_key == key).first()

    def update_reservation_status(
        self, reservation_id: str, status: ReservationStatus, confirmed_at=None
    ) -> Optional[Reservation]:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        if confirmed_at:
            reservation.confirmed_at = confirmed_at
        self.db.flush()
        return reservation

    def list_expired_reservations(self, now) -> list[Reservation]:
        return (
            self.db.query(Reservation)
            .filter(
                Reservation.status == ReservationStatus.PENDING,
                Reservation.expires_at <= now,
            )
            .all()
        )

    # Order operations
    def create_order(
        self, order_id: str, sku_id: str, quantity: int, reservation_id: Optional[str] = None
    ) -> Order:
        order = Order(
            id=order_id,
            sku_id=sku_id,
            quantity=quantity,
            reservation_id=reservation_id,
        )
        self.db.add(order)
        self.db.flush()
        return order

    def get_order(self, order_id: str) -> Optional[Order]:
        return self.db.query(Order).filter(Order.id == order_id).first()

    def list_orders(self, skip: int = 0, limit: int = 20) -> tuple[list[Order], int]:
        query = self.db.query(Order)
        total = query.count()
        orders = query.offset(skip).limit(limit).all()
        return orders, total

    def update_order_status(
        self, order_id: str, status: OrderStatus, confirmed_at=None
    ) -> Optional[Order]:
        order = self.get_order(order_id)
        if not order:
            return None
        order.status = status
        if confirmed_at:
            order.confirmed_at = confirmed_at
        self.db.flush()
        return order

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()
