from datetime import datetime
from commerce_service.repository import Repository
from commerce_service.models import (
    ReservationResponse,
    OrderResponse,
)


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> bool:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict | None:
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> tuple[ReservationResponse, int]:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return (
                ReservationResponse(
                    id=existing["id"],
                    sku=existing["sku"],
                    quantity=existing["quantity"],
                    status=existing["status"],
                    created_at=datetime.fromisoformat(existing["created_at"]),
                    idempotency_key=existing["idempotency_key"],
                ),
                200,
            )

        sku_record = self.repo.get_sku(sku)
        if not sku_record or sku_record["available_stock"] < quantity:
            return None, 400

        if not self.repo.deduct_stock_for_reservation(sku, quantity):
            return None, 400

        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        if not reservation:
            return None, 400

        return (
            ReservationResponse(
                id=reservation["id"],
                sku=reservation["sku"],
                quantity=reservation["quantity"],
                status=reservation["status"],
                created_at=datetime.fromisoformat(reservation["created_at"]),
                idempotency_key=reservation["idempotency_key"],
            ),
            201,
        )

    def confirm_reservation(self, reservation_id: int) -> tuple[dict, int]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return {"detail": "Reservation not found"}, 404

        if reservation["status"] != "PENDING":
            return {"detail": "Reservation is not pending"}, 400

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        elapsed_seconds = (now - created_at).total_seconds()

        if elapsed_seconds > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.restore_stock_from_reservation(
                reservation["sku"], reservation["quantity"]
            )
            return {"detail": "Reservation expired"}, 400

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(
            reservation["sku"], reservation["quantity"], reservation_id
        )

        if not order:
            return {"detail": "Failed to create order"}, 400

        return (
            {
                "reservation_id": reservation_id,
                "order_id": order["id"],
                "sku": order["sku"],
                "quantity": order["quantity"],
                "status": order["status"],
            },
            200,
        )

    def cancel_reservation(self, reservation_id: int) -> tuple[dict, int]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return {"detail": "Reservation not found"}, 404

        if reservation["status"] != "PENDING":
            return {"detail": "Reservation is not pending"}, 400

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        sku_record = self.repo.restore_stock_from_reservation(
            reservation["sku"], reservation["quantity"]
        )

        if not sku_record:
            return {"detail": "Failed to restore stock"}, 400

        return (
            {
                "reservation_id": reservation_id,
                "sku": reservation["sku"],
                "quantity": reservation["quantity"],
                "status": "CANCELLED",
                "restored_stock": sku_record["available_stock"],
            },
            200,
        )

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[OrderResponse], int, int]:
        orders, total = self.repo.get_orders(page, size)
        return (
            [
                OrderResponse(
                    id=order["id"],
                    sku=order["sku"],
                    quantity=order["quantity"],
                    status=order["status"],
                    created_from_reservation_id=order["created_from_reservation_id"],
                    created_at=datetime.fromisoformat(order["created_at"]),
                )
                for order in orders
            ],
            total,
            page,
        )
