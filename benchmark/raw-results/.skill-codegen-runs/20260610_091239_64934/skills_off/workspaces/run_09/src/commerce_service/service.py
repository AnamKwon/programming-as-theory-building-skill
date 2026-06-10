"""Business logic for inventory and order orchestration."""

from datetime import datetime
from typing import Optional

from commerce_service.models import OrderStatus, ReservationStatus
from commerce_service.repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, code: str, name: str) -> dict:
        """Create a new SKU."""
        sku_id = self.repo.create_sku(code, name)
        self.repo.adjust_stock(sku_id, 0)
        return {"id": sku_id, "code": code, "name": name}

    def get_sku(self, sku_id: int) -> dict:
        """Get SKU details."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return sku

    def adjust_stock(self, sku_id: int, quantity: int) -> dict:
        """Adjust stock level."""
        if not self.repo.get_sku(sku_id):
            raise ValueError(f"SKU {sku_id} not found")

        self.repo.adjust_stock(sku_id, quantity)
        stock = self.repo.get_stock(sku_id)
        available = stock["quantity"] - stock["reserved"]

        return {
            "sku_id": sku_id,
            "quantity": stock["quantity"],
            "reserved": stock["reserved"],
            "available": available,
        }

    def create_order(self) -> dict:
        """Create a new order."""
        order_id = self.repo.create_order()
        return {"id": order_id, "status": OrderStatus.PENDING}

    def create_reservation(
        self,
        order_id: int,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        expires_in_seconds: int = 3600,
    ) -> dict:
        """
        Create a reservation with idempotency.
        If the same idempotency key is used, return the existing reservation.
        """
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return self._format_reservation(existing)

        order = self.repo.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        self.repo.expire_old_reservations()

        try:
            reservation_id = self.repo.create_reservation(
                order_id, sku_id, quantity, idempotency_key, expires_in_seconds
            )
        except ValueError as e:
            raise e

        reservation = self.repo.get_reservation(reservation_id)
        return self._format_reservation(reservation)

    def confirm_reservation(self, reservation_id: int) -> dict:
        """Confirm a pending reservation."""
        self.repo.expire_old_reservations()

        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] != ReservationStatus.PENDING:
            raise ValueError(
                f"Cannot confirm reservation in {reservation['status']} status"
            )

        if datetime.fromisoformat(reservation["expires_at"]) < datetime.utcnow():
            self.repo.cancel_reservation(reservation_id)
            raise ValueError("Reservation has expired")

        self.repo.confirm_reservation(reservation_id)
        updated = self.repo.get_reservation(reservation_id)
        return self._format_reservation(updated)

    def cancel_reservation(self, reservation_id: int) -> dict:
        """Cancel a reservation."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] not in (ReservationStatus.PENDING, ReservationStatus.CONFIRMED):
            raise ValueError(
                f"Cannot cancel reservation in {reservation['status']} status"
            )

        self.repo.cancel_reservation(reservation_id)
        updated = self.repo.get_reservation(reservation_id)
        return self._format_reservation(updated)

    def get_order(self, order_id: int) -> dict:
        """Get order with all its reservations."""
        order = self.repo.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        reservations = self.repo.get_order_reservations(order_id)
        items = [
            {
                "reservation_id": r["id"],
                "sku_id": r["sku_id"],
                "quantity": r["quantity"],
                "status": r["status"],
            }
            for r in reservations
        ]

        return {
            "id": order["id"],
            "status": order["status"],
            "created_at": datetime.fromisoformat(order["created_at"]),
            "items": items,
        }

    def list_orders(self, skip: int = 0, limit: int = 20) -> dict:
        """List orders with pagination."""
        orders, total = self.repo.list_orders(skip, limit)
        order_list = []

        for order in orders:
            reservations = self.repo.get_order_reservations(order["id"])
            items = [
                {
                    "reservation_id": r["id"],
                    "sku_id": r["sku_id"],
                    "quantity": r["quantity"],
                    "status": r["status"],
                }
                for r in reservations
            ]
            order_list.append(
                {
                    "id": order["id"],
                    "status": order["status"],
                    "created_at": datetime.fromisoformat(order["created_at"]),
                    "items": items,
                }
            )

        return {
            "items": order_list,
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    def _format_reservation(self, res: dict) -> dict:
        """Format a reservation dict from database."""
        return {
            "id": res["id"],
            "order_id": res["order_id"],
            "sku_id": res["sku_id"],
            "quantity": res["quantity"],
            "status": res["status"],
            "created_at": datetime.fromisoformat(res["created_at"]),
            "expires_at": datetime.fromisoformat(res["expires_at"]),
        }
