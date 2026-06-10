from datetime import datetime, timedelta
from fastapi import HTTPException, status
from commerce_service.repository import Repository
from commerce_service.models import (
    ReservationResponse,
    OrderResponse,
    SKU,
)


RESERVATION_TTL_MINUTES = 30


class CommerceService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku_code: str, name: str, stock_count: int) -> SKU:
        sku = self.repo.create_sku(sku_code, name, stock_count)
        return SKU(id=sku.id, sku_code=sku.sku_code, name=sku.name, stock_count=sku.stock_count)

    def adjust_stock(self, sku_id: int, quantity_delta: int) -> SKU:
        sku = self.repo.update_sku_stock(sku_id, quantity_delta)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )
        return SKU(id=sku.id, sku_code=sku.sku_code, name=sku.name, stock_count=sku.stock_count)

    def create_reservation(self, sku_id: int, quantity: int, idempotency_key: str) -> ReservationResponse:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.sku_id != sku_id or existing.quantity != quantity:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key already used with different request",
                )
            return self._reservation_to_response(existing)

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )

        if sku.stock_count < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock available",
            )

        expires_at = datetime.utcnow() + timedelta(minutes=RESERVATION_TTL_MINUTES)
        reservation = self.repo.create_reservation(sku_id, quantity, idempotency_key, expires_at)
        return self._reservation_to_response(reservation)

    def confirm_reservation(self, reservation_id: int) -> tuple[ReservationResponse, OrderResponse]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation.state != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reservation is not in pending state (current: {reservation.state})",
            )

        if datetime.utcnow() > reservation.expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation has expired",
            )

        sku = self.repo.get_sku(reservation.sku_id)
        if not sku or sku.stock_count < reservation.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock to confirm reservation",
            )

        self.repo.update_sku_stock(reservation.sku_id, -reservation.quantity)
        order = self.repo.create_order(reservation.sku_id, reservation.quantity, "confirmed")
        self.repo.update_reservation_state(reservation_id, "confirmed")

        updated_reservation = self.repo.get_reservation(reservation_id)
        return (
            self._reservation_to_response(updated_reservation),
            self._order_to_response(order),
        )

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation.state == "cancelled":
            return self._reservation_to_response(reservation)

        self.repo.update_reservation_state(reservation_id, "cancelled")
        updated = self.repo.get_reservation(reservation_id)
        return self._reservation_to_response(updated)

    def get_order(self, order_id: int) -> OrderResponse:
        order = self.repo.get_order(order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )
        return self._order_to_response(order)

    def list_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[OrderResponse], int]:
        if page < 1 or page_size < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page and page_size must be >= 1",
            )
        orders, total = self.repo.list_orders(page, page_size)
        return [self._order_to_response(o) for o in orders], total

    @staticmethod
    def _reservation_to_response(reservation) -> ReservationResponse:
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            state=reservation.state,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )

    @staticmethod
    def _order_to_response(order) -> OrderResponse:
        return OrderResponse(
            id=order.id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            state=order.state,
            created_at=order.created_at,
        )
