import time
from fastapi import HTTPException, status
from commerce_service.repository import Repository
from commerce_service.models import ReservationResponse, OrderResponse, OrderListResponse

RESERVATION_EXPIRY_SECONDS = 300

class CommerceService:
    def __init__(self):
        self.repo = Repository()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        self.repo.create_sku(sku, initial_stock)
        return {"sku": sku, "stock": initial_stock}

    def adjust_stock(self, sku: str, amount: int) -> dict:
        stock = self.repo.adjust_stock(sku, amount)
        return {"sku": sku, "stock": stock}

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> ReservationResponse:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return ReservationResponse(**existing)

        current_stock = self.repo.get_sku_stock(sku)
        if current_stock is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SKU not found"
            )
        if current_stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock"
            )

        created_at = time.time()
        reservation_id = self.repo.create_reservation(sku, quantity, idempotency_key, created_at)
        self.repo.adjust_stock(sku, -quantity)

        return ReservationResponse(
            id=reservation_id,
            sku=sku,
            quantity=quantity,
            status="PENDING",
            created_at=created_at
        )

    def confirm_reservation(self, reservation_id: int) -> OrderResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found"
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reservation is not pending"
            )

        current_time = time.time()
        age = current_time - reservation["created_at"]
        if age > RESERVATION_EXPIRY_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired"
            )

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        created_at = time.time()
        order_id = self.repo.create_order(reservation_id, created_at)

        return OrderResponse(
            id=order_id,
            reservation_id=reservation_id,
            created_at=created_at
        )

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found"
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not pending"
            )

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])

        return {"status": "CANCELLED"}

    def get_orders(self, page: int = 1, size: int = 10) -> OrderListResponse:
        offset = (page - 1) * size
        orders, total = self.repo.get_orders(offset, size)
        return OrderListResponse(
            orders=[OrderResponse(**order) for order in orders],
            total=total,
            page=page,
            size=size
        )
