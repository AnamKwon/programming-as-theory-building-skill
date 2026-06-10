from fastapi import Depends, FastAPI, HTTPException, Query, status

from .models import (
    HealthResponse,
    OrderListResponse,
    OrderResponse,
    ReservationConfirmRequest,
    ReservationRequest,
    ReservationResponse,
    SKURequest,
    SKUResponse,
    StockAdjustmentRequest,
    StockAdjustmentResponse,
)
from .repository import Database
from .security import verify_api_key
from .service import ServiceLayer, ValidationError

app = FastAPI(title="Commerce Service", version="0.1.0")
db = Database(db_path="commerce.db")
service = ServiceLayer(db)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse()


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: SKURequest,
    _: str = Depends(verify_api_key),
) -> SKUResponse:
    try:
        sku = service.create_sku(request.sku_code, request.stock_qty)
        return SKUResponse(**sku)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@app.post(
    "/skus/{sku_id}/stock",
    response_model=StockAdjustmentResponse,
)
async def adjust_stock(
    sku_id: int,
    request: StockAdjustmentRequest,
    _: str = Depends(verify_api_key),
) -> StockAdjustmentResponse:
    try:
        sku = service.adjust_stock(sku_id, request.adjustment)
        return StockAdjustmentResponse(**sku)
    except ValidationError as e:
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
) -> ReservationResponse:
    try:
        reservation = service.create_reservation(
            request.sku_code,
            request.qty,
            request.idempotency_key,
        )
        return ReservationResponse(
            id=reservation["id"],
            sku_code=reservation["sku_code"],
            qty=reservation["qty"],
            status=reservation["status"],
            created_at=reservation["created_at"],
            expires_at=reservation["expires_at"],
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=OrderResponse,
)
async def confirm_reservation(
    reservation_id: int,
    request: ReservationConfirmRequest,
    _: str = Depends(verify_api_key),
) -> OrderResponse:
    try:
        _, order = service.confirm_reservation(reservation_id, request.idempotency_key)
        return OrderResponse(
            id=order["id"],
            sku_code=order["sku_code"],
            qty=order["qty"],
            status=order["status"],
            created_at=order["created_at"],
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
) -> ReservationResponse:
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(
            id=reservation["id"],
            sku_code=reservation["sku_code"],
            qty=reservation["qty"],
            status=reservation["status"],
            created_at=reservation["created_at"],
            expires_at=reservation["expires_at"],
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int) -> OrderResponse:
    try:
        order = service.get_order(order_id)
        return OrderResponse(
            id=order["id"],
            sku_code=order["sku_code"],
            qty=order["qty"],
            status=order["status"],
            created_at=order["created_at"],
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> OrderListResponse:
    orders, total = service.list_orders(limit, offset)
    return OrderListResponse(
        orders=[
            OrderResponse(
                id=o["id"],
                sku_code=o["sku_code"],
                qty=o["qty"],
                status=o["status"],
                created_at=o["created_at"],
            )
            for o in orders
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
