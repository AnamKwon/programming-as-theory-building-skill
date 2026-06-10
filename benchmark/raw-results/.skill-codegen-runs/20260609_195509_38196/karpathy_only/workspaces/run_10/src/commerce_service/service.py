from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .models import ReservationStatus
from .repository import InventoryRepository, OrderRepository, ReservationRepository, SKURepository


class CommerceService:
    def __init__(self, db: Session):
        self.db = db
        self.sku_repo = SKURepository(db)
        self.inventory_repo = InventoryRepository(db)
        self.reservation_repo = ReservationRepository(db)
        self.order_repo = OrderRepository(db)

    def create_sku(self, sku_code: str, name: str):
        """Create a new SKU."""
        sku = self.sku_repo.create(sku_code=sku_code, name=name)
        self.inventory_repo.get_or_create(sku.id)
        return sku

    def adjust_stock(self, sku_id: int, quantity_delta: int):
        """Adjust available stock for a SKU."""
        sku = self.sku_repo.get_by_id(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return self.inventory_repo.adjust_available(sku_id, quantity_delta)

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str, ttl_seconds: int
    ):
        """Create a reservation with idempotency support."""
        existing = self.reservation_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == ReservationStatus.EXPIRED:
                raise ValueError("Idempotency key has expired")
            return existing

        sku = self.sku_repo.get_by_id(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        # Try to reserve stock
        if not self.inventory_repo.reserve(sku_id, quantity):
            raise ValueError(f"Insufficient stock for SKU {sku_id}")

        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        reservation = self.reservation_repo.create(
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        return reservation

    def confirm_reservation(self, reservation_id: int):
        """Confirm a reservation, converting it to an order."""
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(f"Cannot confirm reservation with status {reservation.status}")

        if reservation.expires_at <= datetime.utcnow():
            self.reservation_repo.update_status(reservation_id, ReservationStatus.EXPIRED)
            self.inventory_repo.release_reservation(reservation.sku_id, reservation.quantity)
            raise ValueError("Reservation has expired")

        self.inventory_repo.confirm_reservation(reservation.sku_id, reservation.quantity)
        order = self.order_repo.create(
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            reservation_id=reservation_id,
        )
        self.reservation_repo.update_status(reservation_id, ReservationStatus.CONFIRMED)
        return order

    def cancel_reservation(self, reservation_id: int):
        """Cancel a reservation, releasing the reserved stock."""
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(f"Cannot cancel reservation with status {reservation.status}")

        self.inventory_repo.release_reservation(reservation.sku_id, reservation.quantity)
        self.reservation_repo.update_status(reservation_id, ReservationStatus.CANCELLED)
        return reservation

    def get_order(self, order_id: int):
        """Get an order by ID."""
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return order

    def list_orders(self, limit: int = 20, offset: int = 0):
        """List orders with pagination."""
        orders, total = self.order_repo.list_orders(limit=limit, offset=offset)
        return {"orders": orders, "total": total, "limit": limit, "offset": offset}

    def cleanup_expired_reservations(self):
        """Cleanup expired reservations and release their stock."""
        expired = self.reservation_repo.get_expired()
        for res in expired:
            self.inventory_repo.release_reservation(res.sku_id, res.quantity)
            self.reservation_repo.update_status(res.id, ReservationStatus.EXPIRED)
        return len(expired)
