from datetime import datetime
from fastapi import HTTPException, status
from .models import ReservationState, OrderState, ReservationResponse, OrderResponse
from .repository import Repository


class CommerceService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku: str, name: str) -> dict:
        existing = self.repo.get_sku(sku)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"SKU {sku} already exists"
            )
        self.repo.create_sku(sku, name)
        return {"sku": sku, "name": name}

    def adjust_stock(self, sku: str, quantity: int) -> dict:
        existing = self.repo.get_sku(sku)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found"
            )

        stock = self.repo.get_stock(sku)
        self.repo.adjust_stock(sku, quantity)

        new_stock = self.repo.get_stock(sku)
        return {
            "sku": sku,
            "available_quantity": new_stock["available_quantity"],
            "reserved_quantity": new_stock["reserved_quantity"]
        }

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str, ttl_seconds: int) -> ReservationResponse:
        existing = self.repo.get_sku(sku)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found"
            )

        existing_reservation = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing_reservation:
            if existing_reservation["state"] == ReservationState.EXPIRED.value:
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="Reservation already expired"
                )
            return ReservationResponse(
                id=existing_reservation["id"],
                sku=existing_reservation["sku"],
                quantity=existing_reservation["quantity"],
                state=ReservationState(existing_reservation["state"]),
                expires_at=datetime.fromisoformat(existing_reservation["expires_at"]),
                created_at=datetime.fromisoformat(existing_reservation["created_at"])
            )

        stock = self.repo.get_stock(sku)
        if not stock:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No stock available for SKU {sku}"
            )

        available = stock["available_quantity"] - stock["reserved_quantity"]
        if available < quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Insufficient stock: need {quantity}, available {available}"
            )

        reservation_id = self.repo.create_reservation(sku, quantity, idempotency_key, ttl_seconds)
        self.repo.update_stock_reserved(sku, quantity)

        reservation = self.repo.get_reservation(reservation_id)
        return ReservationResponse(
            id=reservation["id"],
            sku=reservation["sku"],
            quantity=reservation["quantity"],
            state=ReservationState(reservation["state"]),
            expires_at=datetime.fromisoformat(reservation["expires_at"]),
            created_at=datetime.fromisoformat(reservation["created_at"])
        )

    def confirm_reservation(self, reservation_id: str) -> OrderResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found"
            )

        if datetime.fromisoformat(reservation["expires_at"]) < datetime.utcnow():
            self.repo.update_reservation_state(reservation_id, ReservationState.EXPIRED.value)
            self.repo.update_stock_reserved(reservation["sku"], -reservation["quantity"])
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Reservation has expired"
            )

        if reservation["state"] != ReservationState.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Reservation already {reservation['state']}"
            )

        self.repo.update_reservation_state(reservation_id, ReservationState.CONFIRMED.value)
        order_id = self.repo.create_order(reservation["sku"], reservation["quantity"], OrderState.CONFIRMED.value)

        order = self.repo.get_order(order_id)
        return OrderResponse(
            id=order["id"],
            sku=order["sku"],
            quantity=order["quantity"],
            state=OrderState(order["state"]),
            created_at=datetime.fromisoformat(order["created_at"])
        )

    def cancel_reservation(self, reservation_id: str) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found"
            )

        if reservation["state"] == ReservationState.CONFIRMED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot cancel confirmed reservation"
            )

        if reservation["state"] == ReservationState.CANCELLED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reservation already cancelled"
            )

        self.repo.update_reservation_state(reservation_id, ReservationState.CANCELLED.value)
        self.repo.update_stock_reserved(reservation["sku"], -reservation["quantity"])

        updated = self.repo.get_reservation(reservation_id)
        return ReservationResponse(
            id=updated["id"],
            sku=updated["sku"],
            quantity=updated["quantity"],
            state=ReservationState(updated["state"]),
            expires_at=datetime.fromisoformat(updated["expires_at"]),
            created_at=datetime.fromisoformat(updated["created_at"])
        )

    def get_order(self, order_id: str) -> OrderResponse:
        order = self.repo.get_order(order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found"
            )
        return OrderResponse(
            id=order["id"],
            sku=order["sku"],
            quantity=order["quantity"],
            state=OrderState(order["state"]),
            created_at=datetime.fromisoformat(order["created_at"])
        )

    def list_orders(self, page: int = 1, page_size: int = 10) -> dict:
        orders, total = self.repo.list_orders(page, page_size)
        return {
            "orders": [
                OrderResponse(
                    id=o["id"],
                    sku=o["sku"],
                    quantity=o["quantity"],
                    state=OrderState(o["state"]),
                    created_at=datetime.fromisoformat(o["created_at"])
                )
                for o in orders
            ],
            "total": total,
            "page": page,
            "page_size": page_size
        }
