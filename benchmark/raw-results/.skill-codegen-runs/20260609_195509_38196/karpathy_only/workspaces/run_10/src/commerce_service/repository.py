from datetime import datetime

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from .models import (
    InventoryModel,
    OrderModel,
    OrderStatus,
    ReservationModel,
    ReservationStatus,
    SKUModel,
)


class SKURepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, sku_code: str, name: str) -> SKUModel:
        sku = SKUModel(sku_code=sku_code, name=name)
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def get_by_id(self, sku_id: int) -> SKUModel | None:
        return self.db.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def get_by_code(self, sku_code: str) -> SKUModel | None:
        return self.db.query(SKUModel).filter(SKUModel.sku_code == sku_code).first()


class InventoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create(self, sku_id: int) -> InventoryModel:
        inv = self.db.query(InventoryModel).filter(InventoryModel.sku_id == sku_id).first()
        if not inv:
            inv = InventoryModel(sku_id=sku_id, available_quantity=0, reserved_quantity=0)
            self.db.add(inv)
            self.db.commit()
            self.db.refresh(inv)
        return inv

    def get_by_sku_id(self, sku_id: int) -> InventoryModel | None:
        return self.db.query(InventoryModel).filter(InventoryModel.sku_id == sku_id).first()

    def adjust_available(self, sku_id: int, delta: int) -> InventoryModel:
        inv = self.get_by_sku_id(sku_id)
        if not inv:
            inv = self.get_or_create(sku_id)
        inv.available_quantity = max(0, inv.available_quantity + delta)
        self.db.commit()
        self.db.refresh(inv)
        return inv

    def reserve(self, sku_id: int, quantity: int) -> bool:
        """Atomically reserve stock. Returns True if successful, False if insufficient stock."""
        inv = self.get_by_sku_id(sku_id)
        if not inv or inv.available_quantity < quantity:
            return False
        inv.available_quantity -= quantity
        inv.reserved_quantity += quantity
        self.db.commit()
        self.db.refresh(inv)
        return True

    def release_reservation(self, sku_id: int, quantity: int) -> None:
        """Release a reservation, returning stock to available."""
        inv = self.get_by_sku_id(sku_id)
        if inv:
            inv.reserved_quantity = max(0, inv.reserved_quantity - quantity)
            inv.available_quantity += quantity
            self.db.commit()
            self.db.refresh(inv)

    def confirm_reservation(self, sku_id: int, quantity: int) -> None:
        """Move stock from reserved to confirmed (order state)."""
        inv = self.get_by_sku_id(sku_id)
        if inv:
            inv.reserved_quantity = max(0, inv.reserved_quantity - quantity)
            self.db.commit()
            self.db.refresh(inv)


class ReservationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        sku_id: int,
        quantity: int,
        expires_at: datetime,
        idempotency_key: str | None = None,
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
            status=ReservationStatus.PENDING,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_by_id(self, reservation_id: int) -> ReservationModel | None:
        return (
            self.db.query(ReservationModel)
            .filter(ReservationModel.id == reservation_id)
            .first()
        )

    def get_by_idempotency_key(self, idempotency_key: str) -> ReservationModel | None:
        return (
            self.db.query(ReservationModel)
            .filter(ReservationModel.idempotency_key == idempotency_key)
            .first()
        )

    def update_status(self, reservation_id: int, status: ReservationStatus) -> ReservationModel:
        reservation = self.get_by_id(reservation_id)
        if reservation:
            reservation.status = status
            self.db.commit()
            self.db.refresh(reservation)
        return reservation

    def get_expired(self) -> list[ReservationModel]:
        """Get all expired reservations still in pending state."""
        return (
            self.db.query(ReservationModel)
            .filter(
                and_(
                    ReservationModel.status == ReservationStatus.PENDING,
                    ReservationModel.expires_at <= datetime.utcnow(),
                )
            )
            .all()
        )


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self, sku_id: int, quantity: int, reservation_id: int | None = None
    ) -> OrderModel:
        order = OrderModel(
            sku_id=sku_id,
            quantity=quantity,
            status=OrderStatus.CONFIRMED,
            reservation_id=reservation_id,
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_by_id(self, order_id: int) -> OrderModel | None:
        return self.db.query(OrderModel).filter(OrderModel.id == order_id).first()

    def list_orders(self, limit: int = 20, offset: int = 0) -> tuple[list[OrderModel], int]:
        """List orders with pagination."""
        query = self.db.query(OrderModel).order_by(desc(OrderModel.created_at))
        total = query.count()
        orders = query.limit(limit).offset(offset).all()
        return orders, total
