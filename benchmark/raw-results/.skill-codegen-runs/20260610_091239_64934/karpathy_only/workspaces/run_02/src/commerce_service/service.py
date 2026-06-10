"""Business logic and service layer."""

from datetime import datetime
from decimal import Decimal
from fastapi import HTTPException
import sqlite3

from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    ReservationStatus,
    OrderStatus,
)
from .repository import Repository, Reservation, Order


class CommerceService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, request: CreateSKURequest) -> dict:
        try:
            sku = self.repo.create_sku(
                sku_id=request.sku_id,
                name=request.name,
                unit_price=request.unit_price,
                stock_quantity=0,
            )
            return {
                "sku_id": sku.sku_id,
                "name": sku.name,
                "unit_price": sku.unit_price,
                "stock_quantity": sku.stock_quantity,
                "created_at": sku.created_at,
            }
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="SKU already exists")

    def get_sku(self, sku_id: str) -> dict:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise HTTPException(status_code=404, detail="SKU not found")
        return {
            "sku_id": sku.sku_id,
            "name": sku.name,
            "unit_price": sku.unit_price,
            "stock_quantity": sku.stock_quantity,
            "created_at": sku.created_at,
        }

    def adjust_stock(self, request: AdjustStockRequest) -> dict:
        sku = self.repo.get_sku(request.sku_id)
        if not sku:
            raise HTTPException(status_code=404, detail="SKU not found")

        new_quantity = sku.stock_quantity + request.quantity_delta
        if new_quantity < 0:
            raise HTTPException(
                status_code=400, detail="Adjustment would result in negative stock"
            )

        self.repo.update_stock(request.sku_id, request.quantity_delta)
        return {
            "sku_id": request.sku_id,
            "previous_quantity": sku.stock_quantity,
            "new_quantity": new_quantity,
        }

    def create_reservation(self, request: CreateReservationRequest) -> ReservationResponse:
        # Idempotency: check for existing reservation with same idempotency key
        existing = self.repo.get_reservation_by_idempotency_key(request.idempotency_key)
        if existing:
            return self._reservation_to_response(existing)

        # Validate SKU exists
        sku = self.repo.get_sku(request.sku_id)
        if not sku:
            raise HTTPException(status_code=404, detail="SKU not found")

        # Check stock availability
        if sku.stock_quantity < request.quantity:
            raise HTTPException(
                status_code=409,
                detail="Insufficient stock",
                headers={"X-Available-Quantity": str(sku.stock_quantity)},
            )

        # Create reservation
        try:
            reservation = self.repo.create_reservation(
                sku_id=request.sku_id,
                quantity=request.quantity,
                idempotency_key=request.idempotency_key,
            )
            return self._reservation_to_response(reservation)
        except sqlite3.IntegrityError:
            # Race condition: another request with same idempotency_key won
            existing = self.repo.get_reservation_by_idempotency_key(request.idempotency_key)
            if existing:
                return self._reservation_to_response(existing)
            raise

    def confirm_reservation(self, reservation_id: str) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        # Check if expired
        if datetime.now() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, "expired")
            raise HTTPException(
                status_code=410, detail="Reservation has expired"
            )

        # Check if already confirmed
        if reservation.status == "confirmed":
            return self._reservation_to_response(reservation)

        # Check if cancelled
        if reservation.status == "cancelled":
            raise HTTPException(
                status_code=400, detail="Reservation is cancelled"
            )

        # Check if expired (status)
        if reservation.status == "expired":
            raise HTTPException(
                status_code=410, detail="Reservation has expired"
            )

        # Verify stock still available
        sku = self.repo.get_sku(reservation.sku_id)
        if not sku or sku.stock_quantity < reservation.quantity:
            raise HTTPException(
                status_code=409, detail="Insufficient stock for confirmation"
            )

        # Reserve stock and confirm
        self.repo.update_stock(reservation.sku_id, -reservation.quantity)
        self.repo.update_reservation_status(reservation_id, "confirmed")

        # Create order
        self.repo.create_order(reservation_id, reservation.sku_id, reservation.quantity)

        # Return updated reservation
        updated = self.repo.get_reservation(reservation_id)
        return self._reservation_to_response(updated)

    def cancel_reservation(self, reservation_id: str) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        # Check if already cancelled
        if reservation.status == "cancelled":
            return self._reservation_to_response(reservation)

        # Check if confirmed (cannot cancel confirmed reservations)
        if reservation.status == "confirmed":
            raise HTTPException(
                status_code=400, detail="Cannot cancel confirmed reservation"
            )

        self.repo.update_reservation_status(reservation_id, "cancelled")
        updated = self.repo.get_reservation(reservation_id)
        return self._reservation_to_response(updated)

    def get_order(self, order_id: str) -> OrderResponse:
        order = self.repo.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        return self._order_to_response(order)

    def list_orders(self, page: int = 1, page_size: int = 20) -> dict:
        if page < 1:
            raise HTTPException(status_code=400, detail="Page must be >= 1")
        if page_size < 1 or page_size > 100:
            raise HTTPException(status_code=400, detail="Page size must be between 1 and 100")

        orders, total = self.repo.list_orders(page=page, page_size=page_size)
        items = [self._order_to_response(o) for o in orders]
        has_more = (page * page_size) < total

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
        }

    @staticmethod
    def _reservation_to_response(reservation: Reservation) -> ReservationResponse:
        return ReservationResponse(
            reservation_id=reservation.reservation_id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=ReservationStatus(reservation.status),
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )

    @staticmethod
    def _order_to_response(order: Order) -> OrderResponse:
        return OrderResponse(
            order_id=order.order_id,
            reservation_id=order.reservation_id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            status=OrderStatus(order.status),
            created_at=order.created_at,
        )
