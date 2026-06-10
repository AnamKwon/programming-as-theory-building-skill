import uuid
from datetime import datetime, timedelta, timezone

from .models import OrderState, ReservationResponse, OrderResponse
from .repository import Repository


class Service:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku_id: str, quantity: int) -> dict:
        """Create a new SKU."""
        self.repo.create_sku(sku_id, quantity)
        return {"sku_id": sku_id, "quantity": quantity}

    def adjust_stock(self, sku_id: str, delta: int) -> dict:
        """Adjust stock for a SKU."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return self.repo.adjust_stock(sku_id, delta)

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str
    ) -> ReservationResponse:
        """Create a reservation, or return existing one if idempotency key matches."""
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return ReservationResponse(
                reservation_id=existing["reservation_id"],
                sku_id=existing["sku_id"],
                quantity=existing["quantity"],
                created_at=existing["created_at"],
                expires_at=existing["expires_at"],
            )

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        if sku["quantity"] < quantity:
            raise ValueError("Insufficient stock")

        reservation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        self.repo.create_reservation(
            reservation_id, sku_id, quantity, idempotency_key, now, expires_at
        )

        return ReservationResponse(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            created_at=now,
            expires_at=expires_at,
        )

    def confirm_reservation(self, reservation_id: str) -> OrderResponse:
        """Confirm a reservation into an order."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["state"] != "CREATED":
            raise ValueError(f"Reservation {reservation_id} is not in CREATED state")

        if datetime.now(timezone.utc) > reservation["expires_at"]:
            raise ValueError(f"Reservation {reservation_id} has expired")

        sku = self.repo.get_sku(reservation["sku_id"])
        if sku["quantity"] < reservation["quantity"]:
            raise ValueError("Insufficient stock (may have been reserved elsewhere)")

        order_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        self.repo.adjust_stock(reservation["sku_id"], -reservation["quantity"])
        self.repo.create_order(
            order_id,
            reservation_id,
            reservation["sku_id"],
            reservation["quantity"],
            now,
        )
        self.repo.confirm_order(order_id, now)
        self.repo.update_reservation_state(reservation_id, "CONFIRMED")

        return OrderResponse(
            order_id=order_id,
            reservation_id=reservation_id,
            sku_id=reservation["sku_id"],
            quantity=reservation["quantity"],
            state=OrderState.CONFIRMED,
            created_at=now,
            confirmed_at=now,
        )

    def cancel_reservation(self, reservation_id: str) -> None:
        """Cancel a reservation."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["state"] != "CREATED":
            raise ValueError(f"Reservation {reservation_id} is not in CREATED state")

        self.repo.update_reservation_state(reservation_id, "CANCELLED")

    def get_orders(self, limit: int, offset: int) -> tuple[list[OrderResponse], int]:
        """List orders with pagination."""
        orders, total = self.repo.list_orders(limit, offset)
        return (
            [
                OrderResponse(
                    order_id=o["order_id"],
                    reservation_id=o["reservation_id"],
                    sku_id=o["sku_id"],
                    quantity=o["quantity"],
                    state=OrderState(o["state"]),
                    created_at=o["created_at"],
                    confirmed_at=o["confirmed_at"],
                )
                for o in orders
            ],
            total,
        )
