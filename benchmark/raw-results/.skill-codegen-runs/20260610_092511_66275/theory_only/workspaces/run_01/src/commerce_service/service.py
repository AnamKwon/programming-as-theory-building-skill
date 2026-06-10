"""Business logic layer. Implements reservation and order rules."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .repository import (
    Database,
    SkuRepository,
    StockRepository,
    ReservationRepository,
    OrderRepository,
)


class CommerceService:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku_id: str, name: str) -> dict:
        session = self.db.get_session()
        try:
            sku_repo = SkuRepository(session)
            sku = sku_repo.create(sku_id, name)
            return {
                "id": sku.id,
                "name": sku.name,
                "created_at": sku.created_at,
            }
        finally:
            session.close()

    def adjust_stock(self, sku_id: str, delta: int) -> dict:
        session = self.db.get_session()
        try:
            sku_repo = SkuRepository(session)
            stock_repo = StockRepository(session)

            if not sku_repo.get(sku_id):
                return None

            stock = stock_repo.adjust_quantity(sku_id, delta)
            return {
                "sku_id": stock.sku_id,
                "quantity": stock.quantity,
                "reserved": stock.reserved,
                "available": stock.quantity - stock.reserved,
            }
        finally:
            session.close()

    def create_reservation(
        self,
        sku_id: str,
        quantity: int,
        ttl_seconds: int = 300,
        idempotency_key: Optional[str] = None,
    ) -> dict | None:
        session = self.db.get_session()
        try:
            sku_repo = SkuRepository(session)
            stock_repo = StockRepository(session)
            reservation_repo = ReservationRepository(session)

            # Verify SKU exists
            if not sku_repo.get(sku_id):
                return None

            # Check for existing reservation by idempotency key
            if idempotency_key:
                existing = reservation_repo.get_by_idempotency_key(idempotency_key)
                if existing:
                    if existing.status == "pending" and existing.expires_at > datetime.utcnow():
                        return {
                            "id": existing.id,
                            "sku_id": existing.sku_id,
                            "quantity": existing.quantity,
                            "status": existing.status,
                            "created_at": existing.created_at,
                            "expires_at": existing.expires_at,
                            "is_duplicate": True,
                        }
                    elif existing.status == "confirmed":
                        return {
                            "id": existing.id,
                            "sku_id": existing.sku_id,
                            "quantity": existing.quantity,
                            "status": existing.status,
                            "created_at": existing.created_at,
                            "expires_at": existing.expires_at,
                            "is_duplicate": True,
                        }

            # Check stock availability
            if not stock_repo.reserve(sku_id, quantity):
                return None  # Insufficient stock

            # Create reservation
            reservation_id = str(uuid.uuid4())
            reservation = reservation_repo.create(
                reservation_id, sku_id, quantity, ttl_seconds, idempotency_key
            )

            if not reservation:
                stock_repo.release_reservation(sku_id, quantity)
                return None

            return {
                "id": reservation.id,
                "sku_id": reservation.sku_id,
                "quantity": reservation.quantity,
                "status": reservation.status,
                "created_at": reservation.created_at,
                "expires_at": reservation.expires_at,
            }
        finally:
            session.close()

    def confirm_reservation(self, reservation_id: str) -> dict | None:
        session = self.db.get_session()
        try:
            reservation_repo = ReservationRepository(session)
            stock_repo = StockRepository(session)
            order_repo = OrderRepository(session)

            reservation = reservation_repo.get(reservation_id)
            if not reservation:
                return None

            if reservation.status != "pending":
                return None

            if reservation.expires_at <= datetime.utcnow():
                reservation_repo.update_status(reservation_id, "expired")
                stock_repo.release_reservation(reservation.sku_id, reservation.quantity)
                return None

            # Confirm: move from reserved to ordered
            stock_repo.confirm_reservation(reservation.sku_id, reservation.quantity)
            reservation_repo.update_status(reservation_id, "confirmed")

            # Create order
            order_id = str(uuid.uuid4())
            order = order_repo.create(order_id, reservation.sku_id, reservation.quantity)

            return {
                "order_id": order.id,
                "sku_id": order.sku_id,
                "quantity": order.quantity,
                "status": order.status,
                "created_at": order.created_at,
            }
        finally:
            session.close()

    def cancel_reservation(self, reservation_id: str) -> bool:
        session = self.db.get_session()
        try:
            reservation_repo = ReservationRepository(session)
            stock_repo = StockRepository(session)

            reservation = reservation_repo.get(reservation_id)
            if not reservation or reservation.status != "pending":
                return False

            stock_repo.release_reservation(reservation.sku_id, reservation.quantity)
            reservation_repo.update_status(reservation_id, "cancelled")
            return True
        finally:
            session.close()

    def get_order(self, order_id: str) -> dict | None:
        session = self.db.get_session()
        try:
            order_repo = OrderRepository(session)
            order = order_repo.get(order_id)
            if not order:
                return None
            return {
                "id": order.id,
                "sku_id": order.sku_id,
                "quantity": order.quantity,
                "status": order.status,
                "created_at": order.created_at,
                "updated_at": order.updated_at,
            }
        finally:
            session.close()

    def list_orders(self, offset: int = 0, limit: int = 20) -> dict:
        session = self.db.get_session()
        try:
            order_repo = OrderRepository(session)
            orders, total = order_repo.list_orders(offset, limit)
            return {
                "items": [
                    {
                        "id": o.id,
                        "sku_id": o.sku_id,
                        "quantity": o.quantity,
                        "status": o.status,
                        "created_at": o.created_at,
                        "updated_at": o.updated_at,
                    }
                    for o in orders
                ],
                "total": total,
                "offset": offset,
                "limit": limit,
            }
        finally:
            session.close()

    def cleanup_expired_reservations(self) -> int:
        session = self.db.get_session()
        try:
            reservation_repo = ReservationRepository(session)
            stock_repo = StockRepository(session)

            expired = reservation_repo.get_expired()
            for reservation in expired:
                stock_repo.release_reservation(reservation.sku_id, reservation.quantity)
                reservation_repo.update_status(reservation.id, "expired")

            return len(expired)
        finally:
            session.close()
