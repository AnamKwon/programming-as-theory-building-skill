from datetime import datetime, timedelta

from commerce_service.models import (
    AdjustStockResponse,
    CreateReservationRequest,
    CreateSKURequest,
    OrderListResponse,
    OrderResponse,
    ReservationResponse,
    SKUResponse,
)
from commerce_service.repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def create_sku(self, request: CreateSKURequest) -> SKUResponse:
        sku_obj = self.repository.create_sku(request.sku, request.initial_stock)
        return SKUResponse(
            id=sku_obj.id,
            sku=sku_obj.sku,
            available_stock=sku_obj.available_stock,
            created_at=sku_obj.created_at,
        )

    def adjust_stock(self, sku: str, amount: int) -> AdjustStockResponse:
        sku_obj = self.repository.update_sku_stock(sku, amount)
        return AdjustStockResponse(
            sku=sku_obj.sku,
            available_stock=sku_obj.available_stock,
        )

    def create_reservation(self, request: CreateReservationRequest) -> ReservationResponse:
        existing = self.repository.get_reservation_by_idempotency_key(request.idempotency_key)
        if existing:
            return ReservationResponse(
                id=existing.id,
                sku=existing.sku,
                quantity=existing.quantity,
                idempotency_key=existing.idempotency_key,
                status=existing.status,
                created_at=existing.created_at,
                updated_at=existing.updated_at,
            )

        sku_obj = self.repository.get_sku_by_name(request.sku)
        if sku_obj.available_stock < request.quantity:
            raise InsufficientStockError("Insufficient stock")

        self.repository.update_sku_stock(request.sku, -request.quantity)
        reservation = self.repository.create_reservation(
            sku_obj.id, request.sku, request.quantity, request.idempotency_key
        )

        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            idempotency_key=reservation.idempotency_key,
            status=reservation.status,
            created_at=reservation.created_at,
            updated_at=reservation.updated_at,
        )

    def confirm_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.repository.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError("Reservation not found")

        if reservation.status != "PENDING":
            raise InvalidStateError(f"Reservation is not in PENDING state: {reservation.status}")

        age_seconds = (datetime.utcnow() - reservation.created_at).total_seconds()
        if age_seconds > 300:
            self.repository.update_reservation_status(reservation_id, "EXPIRED")
            self.repository.update_sku_stock(reservation.sku, reservation.quantity)
            raise ReservationExpiredError("Reservation expired")

        self.repository.update_reservation_status(reservation_id, "CONFIRMED")
        self.repository.create_order(reservation_id, reservation.sku_id, reservation.sku, reservation.quantity)

        reservation = self.repository.get_reservation_by_id(reservation_id)
        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            idempotency_key=reservation.idempotency_key,
            status=reservation.status,
            created_at=reservation.created_at,
            updated_at=reservation.updated_at,
        )

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.repository.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError("Reservation not found")

        if reservation.status != "PENDING":
            raise InvalidStateError(f"Reservation is not in PENDING state: {reservation.status}")

        self.repository.update_reservation_status(reservation_id, "CANCELLED")
        self.repository.update_sku_stock(reservation.sku, reservation.quantity)

        reservation = self.repository.get_reservation_by_id(reservation_id)
        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            idempotency_key=reservation.idempotency_key,
            status=reservation.status,
            created_at=reservation.created_at,
            updated_at=reservation.updated_at,
        )

    def get_orders(self, page: int = 1, size: int = 10) -> OrderListResponse:
        orders, total = self.repository.get_orders(page, size)
        return OrderListResponse(
            items=[
                OrderResponse(
                    id=order.id,
                    reservation_id=order.reservation_id,
                    sku=order.sku,
                    quantity=order.quantity,
                    created_at=order.created_at,
                )
                for order in orders
            ],
            page=page,
            size=size,
            total=total,
        )


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class InvalidStateError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass
