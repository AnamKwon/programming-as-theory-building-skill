from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Optional

from .models import (
    AdjustStockRequest,
    ErrorResponse,
    OrderListResponse,
    OrderResponse,
    OrderItemResponse,
    ReservationRequest,
    ReservationResponse,
    SKURequest,
    SKUResponse,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    Service,
    InsufficientStockError,
    ReservationNotFoundError,
    InvalidReservationStateError,
    OrderNotFoundError,
    DuplicateIdempotencyKeyError,
)

app = FastAPI(title="Commerce Service")

repo = Repository()
service = Service(repo)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: SKURequest,
    _: str = Depends(verify_api_key),
):
    try:
        sku = service.create_sku(request.sku, request.quantity)
        return SKUResponse(
            sku=sku.sku,
            quantity=sku.quantity,
            created_at=sku.created_at,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/skus/{sku}/adjust-stock", response_model=SKUResponse)
async def adjust_stock(
    sku: str,
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
):
    try:
        updated_sku = service.adjust_stock(sku, request.delta)
        return SKUResponse(
            sku=updated_sku.sku,
            quantity=updated_sku.quantity,
            created_at=updated_sku.created_at,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reservation(
    request: ReservationRequest,
    _: str = Depends(verify_api_key),
):
    try:
        reservation = service.create_reservation(
            sku=request.sku,
            quantity=request.quantity,
            idempotency_key=request.idempotency_key,
        )
        return ReservationResponse(
            reservation_id=reservation.reservation_id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except DuplicateIdempotencyKeyError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
):
    try:
        order = service.confirm_reservation(reservation_id)
        return OrderResponse(
            order_id=order.order_id,
            status=order.status,
            items=[OrderItemResponse(sku=item.sku, quantity=item.quantity) for item in order.items],
            created_at=order.created_at,
            updated_at=order.updated_at,
        )
    except ReservationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found",
        )
    except InvalidReservationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(
            reservation_id=reservation.reservation_id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )
    except ReservationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found",
        )
    except InvalidReservationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    cursor: Optional[str] = None,
    limit: int = 20,
    _: str = Depends(verify_api_key),
):
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit must be between 1 and 100",
        )

    orders, next_cursor = service.list_orders(cursor=cursor, limit=limit)
    return OrderListResponse(
        orders=[
            OrderResponse(
                order_id=order.order_id,
                status=order.status,
                items=[
                    OrderItemResponse(sku=item.sku, quantity=item.quantity)
                    for item in order.items
                ],
                created_at=order.created_at,
                updated_at=order.updated_at,
            )
            for order in orders
        ],
        next_cursor=next_cursor,
    )


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    _: str = Depends(verify_api_key),
):
    try:
        order = service.get_order(order_id)
        return OrderResponse(
            order_id=order.order_id,
            status=order.status,
            items=[OrderItemResponse(sku=item.sku, quantity=item.quantity) for item in order.items],
            created_at=order.created_at,
            updated_at=order.updated_at,
        )
    except OrderNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found",
        )


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(code="validation_error", message=str(exc)).dict(),
    )
