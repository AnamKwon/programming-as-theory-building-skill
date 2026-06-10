from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from .models import (
    AdjustStockRequest,
    CancelReservationRequest,
    ConfirmReservationRequest,
    CreateReservationRequest,
    CreateSKURequest,
    HealthResponse,
    OrderItemResponse,
    OrderResponse,
    OrderStatus,
    PaginatedOrdersResponse,
    ReservationResponse,
    ReservationStatus,
    SKUResponse,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    CommerceService,
    IdempotencyKeyAlreadyUsedError,
    InsufficientStockError,
    InvalidTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")
repo = Repository()
service = CommerceService(repo)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")


@app.post("/skus", response_model=SKUResponse)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key),
):
    try:
        sku_model = service.create_sku(
            sku=request.sku,
            description=request.description,
            quantity=request.quantity,
        )
        return SKUResponse(
            sku=sku_model.sku,
            description=sku_model.description,
            quantity=sku_model.quantity,
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail=f"SKU {request.sku} already exists")


@app.get("/skus/{sku}", response_model=SKUResponse)
async def get_sku(sku: str):
    sku_model = service.get_sku(sku)
    if not sku_model:
        raise HTTPException(status_code=404, detail=f"SKU {sku} not found")
    return SKUResponse(
        sku=sku_model.sku,
        description=sku_model.description,
        quantity=sku_model.quantity,
    )


@app.post("/skus/{sku}/adjust", response_model=SKUResponse)
async def adjust_stock(
    sku: str,
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key),
):
    try:
        sku_model = service.adjust_stock(sku, request.adjustment)
        return SKUResponse(
            sku=sku_model.sku,
            description=sku_model.description,
            quantity=sku_model.quantity,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key),
):
    try:
        reservation = service.create_reservation(
            order_id=request.order_id,
            sku=request.sku,
            quantity=request.quantity,
            idempotency_key=request.idempotency_key,
        )
        return ReservationResponse(
            reservation_id=reservation.reservation_id,
            order_id=reservation.order_id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=ReservationStatus(reservation.status),
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: str,
    request: ConfirmReservationRequest,
    api_key: str = Depends(verify_api_key),
):
    try:
        reservation = service.confirm_reservation(reservation_id)
        return ReservationResponse(
            reservation_id=reservation.reservation_id,
            order_id=reservation.order_id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=ReservationStatus(reservation.status),
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
        )
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    request: CancelReservationRequest,
    api_key: str = Depends(verify_api_key),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(
            reservation_id=reservation.reservation_id,
            order_id=reservation.order_id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=ReservationStatus(reservation.status),
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
        )
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/orders", response_model=PaginatedOrdersResponse)
async def list_orders(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    api_key: str = Depends(verify_api_key),
):
    orders, total = service.list_orders(limit=limit, offset=offset)
    order_responses = []
    for order in orders:
        reservations = service.get_reservations_for_order(order.order_id)
        items = [
            OrderItemResponse(
                reservation_id=r.reservation_id,
                sku=r.sku,
                quantity=r.quantity,
                status=ReservationStatus(r.status),
            )
            for r in reservations
        ]
        order_responses.append(
            OrderResponse(
                order_id=order.order_id,
                status=OrderStatus(order.status),
                items=items,
                created_at=order.created_at,
            )
        )
    return PaginatedOrdersResponse(
        orders=order_responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, api_key: str = Depends(verify_api_key)):
    try:
        order = service.get_order(order_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    reservations = service.get_reservations_for_order(order_id)
    items = [
        OrderItemResponse(
            reservation_id=r.reservation_id,
            sku=r.sku,
            quantity=r.quantity,
            status=ReservationStatus(r.status),
        )
        for r in reservations
    ]
    return OrderResponse(
        order_id=order.order_id,
        status=OrderStatus(order.status),
        items=items,
        created_at=order.created_at,
    )
