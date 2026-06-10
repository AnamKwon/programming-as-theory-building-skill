from fastapi import FastAPI, HTTPException, Depends, Query, status, Response
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
import json

from .models import (
    CreateSKURequest,
    CreateSKUResponse,
    AdjustStockRequest,
    AdjustStockResponse,
    CreateReservationRequest,
    CreateReservationResponse,
    ConfirmReservationRequest,
    ConfirmReservationResponse,
    CancelReservationRequest,
    CancelReservationResponse,
    OrderListResponse,
    OrderResponse,
)
from .repository import Repository
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    InvalidReservationStateError,
)
from .security import verify_api_key

app = FastAPI(title="Commerce Service", version="0.1.0")
repo = Repository()
service = CommerceService(repo)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=CreateSKUResponse, status_code=status.HTTP_201_CREATED)
def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_key),
):
    try:
        sku = service.create_sku(request.id, request.available_stock)
        return CreateSKUResponse(
            id=sku.id,
            available_stock=sku.available_stock,
            reserved_stock=sku.reserved_stock,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/skus/{sku_id}/stock", response_model=AdjustStockResponse)
def adjust_stock(
    sku_id: str,
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
):
    try:
        sku = service.adjust_stock(sku_id, request.delta)
        return AdjustStockResponse(
            id=sku.id,
            available_stock=sku.available_stock,
            reserved_stock=sku.reserved_stock,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations", response_model=CreateReservationResponse)
def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_key),
):
    try:
        reservation, is_new = service.create_reservation(
            request.sku_id,
            request.quantity,
            request.idempotency_key,
        )
        response_data = CreateReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=reservation.status,
            expires_at=reservation.expires_at,
        )
        status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
        return Response(
            content=json.dumps(jsonable_encoder(response_data)),
            status_code=status_code,
            media_type="application/json",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/confirm", response_model=ConfirmReservationResponse)
def confirm_reservation(
    reservation_id: str,
    request: ConfirmReservationRequest,
    _: str = Depends(verify_api_key),
):
    try:
        order = service.confirm_reservation(reservation_id)
        return ConfirmReservationResponse(
            id=reservation_id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            status=order.status,
            order_id=order.id,
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


@app.post("/reservations/{reservation_id}/cancel", response_model=CancelReservationResponse)
def cancel_reservation(
    reservation_id: str,
    request: CancelReservationRequest,
    _: str = Depends(verify_api_key),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return CancelReservationResponse(
            id=reservation.id,
            status=reservation.status,
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
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    orders, total = service.list_orders(page, page_size)
    return OrderListResponse(
        orders=[
            OrderResponse(
                id=order.id,
                reservation_id=order.reservation_id,
                sku_id=order.sku_id,
                quantity=order.quantity,
                status=order.status,
                created_at=order.created_at,
            )
            for order in orders
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
