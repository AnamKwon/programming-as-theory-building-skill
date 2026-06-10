from datetime import datetime
from .repository import Repository
from .models import ReservationState, ReservationResponse, OrderResponse


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> None:
        if initial_stock < 0:
            raise ValueError("Initial stock cannot be negative")
        self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, quantity: int) -> None:
        on_hand_reserved = self.repo.get_sku(sku)
        if not on_hand_reserved:
            raise ValueError(f"SKU {sku} not found")

        on_hand, reserved = on_hand_reserved
        new_on_hand = on_hand + quantity

        if new_on_hand < reserved:
            raise ValueError(
                f"Cannot reduce stock below reserved amount. "
                f"On-hand after adjustment: {new_on_hand}, Reserved: {reserved}"
            )

        self.repo.adjust_stock(sku, quantity)

    def create_reservation(
        self, sku: str, units: int, idempotency_key: str
    ) -> ReservationResponse:
        if units <= 0:
            raise ValueError("Units must be positive")

        sku_data = self.repo.get_sku(sku)
        if not sku_data:
            raise ValueError(f"SKU {sku} not found")

        on_hand, reserved = sku_data
        if on_hand < units:
            raise ValueError(
                f"Insufficient stock. Available: {on_hand}, Requested: {units}"
            )

        reservation_id, expires_at = self.repo.create_reservation(
            sku, units, idempotency_key
        )

        return ReservationResponse(
            reservation_id=reservation_id,
            sku=sku,
            units=units,
            state=ReservationState.PENDING,
            expires_at=expires_at,
            created_at=datetime.utcnow(),
        )

    def get_reservation(self, reservation_id: str) -> ReservationResponse:
        res = self.repo.get_reservation(reservation_id)
        if not res:
            raise ValueError(f"Reservation {reservation_id} not found")

        return ReservationResponse(
            reservation_id=res["reservation_id"],
            sku=res["sku"],
            units=res["units"],
            state=ReservationState(res["state"]),
            expires_at=res["expires_at"],
            created_at=res["created_at"],
        )

    def confirm_reservation(self, reservation_id: str) -> OrderResponse:
        res = self.repo.get_reservation(reservation_id)
        if not res:
            raise ValueError(f"Reservation {reservation_id} not found")

        if datetime.utcnow() > res["expires_at"]:
            raise ValueError("Reservation has expired")

        order_id = self.repo.confirm_reservation(reservation_id)

        return OrderResponse(
            order_id=order_id,
            sku=res["sku"],
            units=res["units"],
            created_at=datetime.utcnow(),
            confirmed_at=datetime.utcnow(),
        )

    def cancel_reservation(self, reservation_id: str) -> None:
        res = self.repo.get_reservation(reservation_id)
        if not res:
            raise ValueError(f"Reservation {reservation_id} not found")

        self.repo.cancel_reservation(reservation_id)

    def get_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[OrderResponse], int]:
        if limit < 1 or limit > 100:
            raise ValueError("Limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("Offset must be non-negative")

        orders = self.repo.get_orders(limit, offset)
        total = self.repo.get_total_orders()

        order_responses = [
            OrderResponse(
                order_id=o["order_id"],
                sku=o["sku"],
                units=o["units"],
                created_at=o["created_at"],
                confirmed_at=o["confirmed_at"],
            )
            for o in orders
        ]

        return order_responses, total
