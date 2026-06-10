from fastapi import FastAPI, Depends, HTTPException, status, Query
from commerce_service.models import (
    HealthResponse,
    SKUCreate,
    SKUResponse,
    StockAdjust,
    ReservationCreate,
    ReservationResponse,
    ReservationConfirm,
    OrderResponse,
    OrderListResponse,
)
from commerce_service.repository import Repository
from commerce_service.service import CommerceService, InsufficientStockError, ReservationExpiredError, InvalidStateTransitionError, IdempotencyKeyConflictError
from commerce_service.security import validate_api_key

app = FastAPI(title="Commerce Service", version="0.1.0")

repo = Repository()
service = CommerceService(repo)


@app.get("/health", response_model=HealthResponse)
def health_check():
    return {"status": "healthy", "message": "Service is operational"}


@app.post("/skus", response_model=SKUResponse, dependencies=[Depends(validate_api_key)])
def create_sku(payload: SKUCreate):
    try:
        sku = service.create_sku(payload.sku_code, payload.name)
        return SKUResponse(
            id=sku.id,
            sku_code=sku.sku_code,
            name=sku.name,
            available_quantity=sku.available_quantity,
            reserved_quantity=sku.reserved_quantity,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/stock/adjust", response_model=SKUResponse, dependencies=[Depends(validate_api_key)])
def adjust_stock(payload: StockAdjust):
    try:
        sku = service.adjust_stock(payload.sku_id, payload.quantity_delta)
        return SKUResponse(
            id=sku.id,
            sku_code=sku.sku_code,
            name=sku.name,
            available_quantity=sku.available_quantity,
            reserved_quantity=sku.reserved_quantity,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, dependencies=[Depends(validate_api_key)])
def create_reservation(payload: ReservationCreate):
    try:
        order = service.create_reservation(payload.sku_id, payload.quantity, payload.idempotency_key)
        return ReservationResponse(
            id=order.id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            status=order.status,
            created_at=order.created_at,
            expires_at=order.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except IdempotencyKeyConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{order_id}/confirm", response_model=ReservationResponse, dependencies=[Depends(validate_api_key)])
def confirm_reservation(order_id: int):
    try:
        order = service.confirm_reservation(order_id)
        return ReservationResponse(
            id=order.id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            status=order.status,
            created_at=order.created_at,
            expires_at=order.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{order_id}/cancel", response_model=ReservationResponse, dependencies=[Depends(validate_api_key)])
def cancel_reservation(order_id: int):
    try:
        order = service.cancel_reservation(order_id)
        return ReservationResponse(
            id=order.id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            status=order.status,
            created_at=order.created_at,
            expires_at=order.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def list_orders(page: int = Query(1, ge=1), per_page: int = Query(10, ge=1, le=100)):
    orders, total = repo.list_orders(page=page, per_page=per_page)
    return OrderListResponse(
        orders=[
            OrderResponse(
                id=order.id,
                sku_id=order.sku_id,
                quantity=order.quantity,
                status=order.status,
                created_at=order.created_at,
                expires_at=order.expires_at,
            )
            for order in orders
        ],
        total=total,
        page=page,
        per_page=per_page,
    )
