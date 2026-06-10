"""Business logic layer for the commerce service."""

from datetime import datetime
from typing import List, Optional, Tuple

from .models import OrderResponse, ReservationResponse, ReservationStatus, OrderStatus, SKUResponse
from .repository import Database


class CommerceService:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku_id: str, name: str, price: float, initial_stock: int) -> SKUResponse:
        """Create a new SKU with initial stock."""
        success = self.db.create_sku(sku_id, name, price)
        if not success:
            raise ValueError(f"SKU {sku_id} already exists")

        self.db.set_inventory(sku_id, initial_stock)

        sku = self.db.get_sku(sku_id)
        return SKUResponse(
            sku_id=sku["sku_id"],
            name=sku["name"],
            price=sku["price"],
            created_at=datetime.fromisoformat(sku["created_at"]),
        )

    def adjust_stock(self, sku_id: str, quantity_delta: int) -> dict:
        """Adjust inventory stock."""
        sku = self.db.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        inv = self.db.get_inventory(sku_id)
        if not inv:
            raise ValueError(f"No inventory for SKU {sku_id}")

        new_available = inv["available_quantity"] + quantity_delta
        if new_available < 0:
            raise ValueError("Insufficient available inventory to reduce")

        self.db.set_inventory(sku_id, new_available, inv["reserved_quantity"])

        return {
            "sku_id": sku_id,
            "available_quantity": new_available,
            "reserved_quantity": inv["reserved_quantity"],
        }

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str
    ) -> ReservationResponse:
        """Create a reservation, or return existing if idempotency key matches."""
        # Check for existing reservation with same idempotency key
        existing = self.db.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return self._reservation_row_to_response(existing)

        # Validate SKU exists
        sku = self.db.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        # Get current inventory
        inv = self.db.get_inventory(sku_id)
        if not inv:
            raise ValueError(f"No inventory for SKU {sku_id}")

        # Check stock availability
        if inv["available_quantity"] < quantity:
            raise ValueError(
                f"Insufficient stock. Available: {inv['available_quantity']}, Requested: {quantity}"
            )

        # Reserve inventory
        success = self.db.reserve_inventory(sku_id, quantity)
        if not success:
            raise ValueError("Failed to reserve inventory (concurrent conflict)")

        # Create reservation
        reservation_id = self.db.create_reservation(sku_id, quantity, idempotency_key)
        reservation = self.db.get_reservation(reservation_id)

        return self._reservation_row_to_response(reservation)

    def confirm_reservation(self, reservation_id: str) -> ReservationResponse:
        """Confirm a reservation and create an order."""
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        # Check expiration
        if reservation["status"] == ReservationStatus.EXPIRED:
            raise ValueError(f"Reservation {reservation_id} has expired")

        if reservation["status"] != ReservationStatus.PENDING:
            raise ValueError(
                f"Cannot confirm reservation in {reservation['status']} status"
            )

        # Confirm reservation
        success = self.db.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)
        if not success:
            raise ValueError("Failed to confirm reservation")

        # Confirm inventory (move from reserved to confirmed)
        confirm_success = self.db.confirm_reservation(
            reservation["sku_id"], reservation["quantity"]
        )
        if not confirm_success:
            # Rollback reservation status
            self.db.update_reservation_status(reservation_id, ReservationStatus.PENDING)
            raise ValueError("Failed to confirm inventory")

        # Create order
        self.db.create_order(reservation["sku_id"], reservation["quantity"], reservation_id)

        reservation = self.db.get_reservation(reservation_id)
        return self._reservation_row_to_response(reservation)

    def cancel_reservation(self, reservation_id: str) -> ReservationResponse:
        """Cancel a reservation and release inventory."""
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] != ReservationStatus.PENDING:
            raise ValueError(
                f"Cannot cancel reservation in {reservation['status']} status"
            )

        # Release inventory
        success = self.db.release_reservation(reservation["sku_id"], reservation["quantity"])
        if not success:
            raise ValueError("Failed to release inventory")

        # Update status
        self.db.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

        reservation = self.db.get_reservation(reservation_id)
        return self._reservation_row_to_response(reservation)

    def get_orders(self, skip: int = 0, limit: int = 10) -> Tuple[List[OrderResponse], int]:
        """Get paginated list of orders."""
        orders, total = self.db.list_orders(skip, limit)
        responses = [
            OrderResponse(
                order_id=order["order_id"],
                sku_id=order["sku_id"],
                quantity=order["quantity"],
                status=OrderStatus[order["status"].upper()],
                created_at=datetime.fromisoformat(order["created_at"]),
                reservation_id=order["reservation_id"],
            )
            for order in orders
        ]
        return responses, total

    @staticmethod
    def _reservation_row_to_response(row: dict) -> ReservationResponse:
        """Convert database row to response model."""
        return ReservationResponse(
            reservation_id=row["reservation_id"],
            sku_id=row["sku_id"],
            quantity=row["quantity"],
            status=ReservationStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
        )
