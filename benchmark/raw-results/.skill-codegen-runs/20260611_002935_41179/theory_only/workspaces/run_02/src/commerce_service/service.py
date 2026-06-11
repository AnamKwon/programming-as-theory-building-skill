from datetime import datetime, timedelta
from fastapi import HTTPException, status
from commerce_service.repository import Repository
from commerce_service.models import (
    SKUCreate, SKUResponse, StockAdjustRequest, ReservationCreate,
    ReservationResponse, OrderResponse, OrderListResponse
)


class CommerceService:
    RESERVATION_EXPIRY_SECONDS = 300

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, request: SKUCreate) -> SKUResponse:
        result = self.repo.create_sku(request.sku, request.initial_stock)
        return SKUResponse(**result)

    def adjust_stock(self, request: StockAdjustRequest) -> dict:
        sku_data = self.repo.get_sku(request.sku)
        if not sku_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {request.sku} not found"
            )

        result = self.repo.adjust_stock(request.sku, request.amount)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {request.sku} not found"
            )
        return {'available_stock': result['available_stock'], 'reserved_stock': result['reserved_stock']}

    def create_reservation(self, request: ReservationCreate) -> ReservationResponse:
        sku_data = self.repo.get_sku(request.sku)
        if not sku_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {request.sku} not found"
            )

        existing = self.repo.get_reservation_by_idempotency_key(request.idempotency_key)
        if existing:
            return ReservationResponse(
                id=existing['id'],
                sku=existing['sku'],
                quantity=existing['quantity'],
                status=existing['status'],
                created_at=datetime.fromisoformat(existing['created_at']),
                idempotency_key=existing['idempotency_key']
            )

        if sku_data['available_stock'] < request.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock"
            )

        result = self.repo.create_reservation(request.sku, request.quantity, request.idempotency_key)
        return ReservationResponse(
            id=result['id'],
            sku=result['sku'],
            quantity=result['quantity'],
            status=result['status'],
            created_at=datetime.fromisoformat(result['created_at']),
            idempotency_key=result['idempotency_key']
        )

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found"
            )

        if reservation['status'] != 'PENDING':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reservation is not in PENDING state (current: {reservation['status']})"
            )

        created_at = datetime.fromisoformat(reservation['created_at'])
        now = datetime.utcnow()
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > self.RESERVATION_EXPIRY_SECONDS:
            self.repo.update_reservation_status(reservation_id, 'EXPIRED')
            self.repo.restore_reserved_stock(reservation['sku'], reservation['quantity'])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired"
            )

        self.repo.update_reservation_status(reservation_id, 'CONFIRMED')
        order = self.repo.create_order(reservation_id, reservation['sku'], reservation['quantity'])

        return {
            'id': reservation_id,
            'sku': reservation['sku'],
            'quantity': reservation['quantity'],
            'status': 'CONFIRMED',
            'order_id': order['id']
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found"
            )

        if reservation['status'] != 'PENDING':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reservation is not in PENDING state (current: {reservation['status']})"
            )

        self.repo.update_reservation_status(reservation_id, 'CANCELLED')
        self.repo.restore_reserved_stock(reservation['sku'], reservation['quantity'])

        return {'id': reservation_id, 'status': 'CANCELLED'}

    def get_orders(self, page: int = 1, size: int = 10) -> OrderListResponse:
        orders, total = self.repo.get_orders(page, size)
        order_responses = [
            OrderResponse(
                id=order['id'],
                reservation_id=order['reservation_id'],
                sku=order['sku'],
                quantity=order['quantity'],
                created_at=datetime.fromisoformat(order['created_at'])
            )
            for order in orders
        ]
        return OrderListResponse(total=total, page=page, size=size, orders=order_responses)
