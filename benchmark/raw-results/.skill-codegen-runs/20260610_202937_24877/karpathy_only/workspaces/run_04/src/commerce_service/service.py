from datetime import datetime, timezone
from fastapi import HTTPException, status
from .repository import Repository
from .models import ReservationResponse, OrderResponse, OrdersListResponse


class CommerceService:
    EXPIRATION_SECONDS = 300

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku: str, initial_stock: int):
        existing = self.repo.get_sku_by_name(sku)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="SKU already exists",
            )
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int):
        existing = self.repo.get_sku_by_name(sku)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> ReservationResponse:
        existing_reservation = self.repo.get_reservation_by_idempotency_key(
            idempotency_key
        )
        if existing_reservation:
            return ReservationResponse(
                id=existing_reservation.id,
                sku=existing_reservation.sku,
                quantity=existing_reservation.quantity,
                status=existing_reservation.status,
                created_at=existing_reservation.created_at,
                idempotency_key=existing_reservation.idempotency_key,
            )

        available = self.repo.get_available_stock(sku)
        if available < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
            idempotency_key=reservation.idempotency_key,
        )

    def confirm_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not in PENDING state",
            )

        now = datetime.now(timezone.utc)
        created_at_utc = reservation.created_at.replace(tzinfo=timezone.utc)
        age_seconds = (now - created_at_utc).total_seconds()

        if age_seconds > self.EXPIRATION_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation.sku, reservation.quantity)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        self.repo.create_order(reservation_id)

        updated_reservation = self.repo.get_reservation_by_id(reservation_id)
        return ReservationResponse(
            id=updated_reservation.id,
            sku=updated_reservation.sku,
            quantity=updated_reservation.quantity,
            status=updated_reservation.status,
            created_at=updated_reservation.created_at,
            idempotency_key=updated_reservation.idempotency_key,
        )

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not in PENDING state",
            )

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.adjust_stock(reservation.sku, reservation.quantity)

        updated_reservation = self.repo.get_reservation_by_id(reservation_id)
        return ReservationResponse(
            id=updated_reservation.id,
            sku=updated_reservation.sku,
            quantity=updated_reservation.quantity,
            status=updated_reservation.status,
            created_at=updated_reservation.created_at,
            idempotency_key=updated_reservation.idempotency_key,
        )

    def get_orders(self, page: int = 1, size: int = 10) -> OrdersListResponse:
        if page < 1:
            page = 1
        if size < 1:
            size = 10

        orders, total = self.repo.get_orders(page, size)
        return OrdersListResponse(
            orders=[
                OrderResponse(
                    id=order.id,
                    reservation_id=order.reservation_id,
                    created_at=order.created_at,
                )
                for order in orders
            ],
            page=page,
            size=size,
            total=total,
        )
