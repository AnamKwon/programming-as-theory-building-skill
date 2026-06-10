from datetime import datetime, timezone
from fastapi import HTTPException, status

from .repository import Database, SKURepository, ReservationRepository, OrderRepository
from .models import ReservationResponse, OrderResponse


class CommerceService:
    def __init__(self, db: Database):
        self.db = db
        self.sku_repo = SKURepository(db)
        self.reservation_repo = ReservationRepository(db)
        self.order_repo = OrderRepository(db)

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.sku_repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        sku_record = self.sku_repo.get_sku_by_sku(sku)
        if not sku_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )
        return self.sku_repo.update_stock(sku_record["id"], amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> ReservationResponse:
        existing = self.reservation_repo.get_reservation_by_idempotency_key(
            idempotency_key
        )
        if existing:
            return ReservationResponse(
                id=existing["id"],
                sku=existing["sku"],
                quantity=existing["quantity"],
                status=existing["status"],
                idempotency_key=existing["idempotency_key"],
                created_at=existing["created_at"],
            )

        sku_record = self.sku_repo.get_sku_by_sku(sku)
        if not sku_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )

        if sku_record["available_stock"] < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        now_utc = datetime.now(timezone.utc).isoformat()
        self.sku_repo.update_stock(sku_record["id"], -quantity)

        reservation = self.reservation_repo.create_reservation(
            sku_record["id"],
            sku,
            quantity,
            idempotency_key,
            now_utc,
        )

        return ReservationResponse(
            id=reservation["id"],
            sku=reservation["sku"],
            quantity=reservation["quantity"],
            status=reservation["status"],
            idempotency_key=reservation["idempotency_key"],
            created_at=reservation["created_at"],
        )

    def confirm_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.reservation_repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not pending",
            )

        created_at = datetime.fromisoformat(reservation["created_at"])
        now_utc = datetime.now(timezone.utc)
        age_seconds = (now_utc - created_at).total_seconds()

        if age_seconds > 300:
            self.reservation_repo.update_reservation_status(
                reservation_id, "EXPIRED"
            )
            sku_record = self.sku_repo.get_sku_by_sku(reservation["sku"])
            if sku_record:
                self.sku_repo.update_stock(sku_record["id"], reservation["quantity"])

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        updated = self.reservation_repo.update_reservation_status(
            reservation_id, "CONFIRMED"
        )

        now_utc_iso = datetime.now(timezone.utc).isoformat()
        self.order_repo.create_order(reservation_id, now_utc_iso)

        return ReservationResponse(
            id=updated["id"],
            sku=updated["sku"],
            quantity=updated["quantity"],
            status=updated["status"],
            idempotency_key=updated["idempotency_key"],
            created_at=updated["created_at"],
        )

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.reservation_repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not pending",
            )

        updated = self.reservation_repo.update_reservation_status(
            reservation_id, "CANCELLED"
        )

        sku_record = self.sku_repo.get_sku_by_sku(reservation["sku"])
        if sku_record:
            self.sku_repo.update_stock(sku_record["id"], reservation["quantity"])

        return ReservationResponse(
            id=updated["id"],
            sku=updated["sku"],
            quantity=updated["quantity"],
            status=updated["status"],
            idempotency_key=updated["idempotency_key"],
            created_at=updated["created_at"],
        )

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        if page < 1:
            page = 1
        if size < 1:
            size = 10

        orders, total = self.order_repo.list_orders(page, size)
        order_responses = [
            OrderResponse(
                id=order["id"],
                reservation_id=order["reservation_id"],
                created_at=order["created_at"],
            )
            for order in orders
        ]

        return {
            "items": order_responses,
            "page": page,
            "size": size,
            "total": total,
        }
