import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from commerce_service.repository import Repository


class CommercService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, name: str, initial_stock: int) -> dict:
        session = self.repo.get_session()
        try:
            existing = self.repo.get_sku(session, sku_id)
            if existing:
                raise ValueError(f"SKU {sku_id} already exists")
            sku = self.repo.create_sku(session, sku_id, name, initial_stock)
            return {"sku_id": sku.id, "name": sku.name, "created_at": sku.created_at.isoformat()}
        finally:
            session.close()

    def adjust_stock(self, sku_id: str, delta: int) -> dict:
        session = self.repo.get_session()
        try:
            stock = self.repo.adjust_stock(session, sku_id, delta)
            return {"sku_id": sku_id, "available": stock.available, "reserved": stock.reserved}
        finally:
            session.close()

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str, ttl_seconds: int
    ) -> dict:
        session = self.repo.get_session()
        try:
            existing = self.repo.get_reservation_by_idempotency_key(session, idempotency_key)
            if existing:
                return {
                    "id": existing.id,
                    "sku_id": existing.sku_id,
                    "quantity": existing.quantity,
                    "status": existing.status,
                    "created_at": existing.created_at.isoformat(),
                    "expires_at": existing.expires_at.isoformat(),
                }

            stock = self.repo.get_stock(session, sku_id)
            if not stock:
                raise ValueError(f"SKU {sku_id} not found")
            if stock.available < quantity:
                raise ValueError(f"Insufficient stock: need {quantity}, have {stock.available}")

            res_id = str(uuid.uuid4())
            expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
            res = self.repo.create_reservation(session, res_id, sku_id, quantity, idempotency_key, expires_at)

            return {
                "id": res.id,
                "sku_id": res.sku_id,
                "quantity": res.quantity,
                "status": res.status,
                "created_at": res.created_at.isoformat(),
                "expires_at": res.expires_at.isoformat(),
            }
        finally:
            session.close()

    def confirm_reservation(self, res_id: str) -> dict:
        session = self.repo.get_session()
        try:
            order_id = str(uuid.uuid4())
            order = self.repo.confirm_reservation(session, res_id, order_id)
            return {
                "id": order.id,
                "sku_id": order.sku_id,
                "quantity": order.quantity,
                "created_at": order.created_at.isoformat(),
            }
        finally:
            session.close()

    def cancel_reservation(self, res_id: str) -> dict:
        session = self.repo.get_session()
        try:
            res = self.repo.cancel_reservation(session, res_id)
            return {
                "id": res.id,
                "sku_id": res.sku_id,
                "quantity": res.quantity,
                "status": res.status,
                "created_at": res.created_at.isoformat(),
                "expires_at": res.expires_at.isoformat(),
            }
        finally:
            session.close()

    def list_orders(self, skip: int, limit: int) -> dict:
        session = self.repo.get_session()
        try:
            orders, total = self.repo.list_orders(session, skip, limit)
            return {
                "items": [
                    {
                        "id": o.id,
                        "sku_id": o.sku_id,
                        "quantity": o.quantity,
                        "created_at": o.created_at.isoformat(),
                    }
                    for o in orders
                ],
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        finally:
            session.close()
