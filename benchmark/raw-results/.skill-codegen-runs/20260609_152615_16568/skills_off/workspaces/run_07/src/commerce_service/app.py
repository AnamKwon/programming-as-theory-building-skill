from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse

from .models import (
    HealthResponse,
    SKURequest,
    SKUResponse,
    StockAdjustmentRequest,
    ReservationCreateRequest,
    ReservationResponse,
    ReservationActionRequest,
    OrderResponse,
    OrderListResponse,
)
from .repository import Database
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    OrderNotFoundError,
)
from .security import verify_api_key

app = FastAPI(title="Commerce Service", version="0.1.0")
db = Database("commerce.db")
service = CommerceService(db)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    request: SKURequest,
    api_key: str = Depends(verify_api_key),
):
    try:
        result = service.create_sku(request.sku, request.name)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/stock/adjust", status_code=200)
async def adjust_stock(
    request: StockAdjustmentRequest,
    api_key: str = Depends(verify_api_key),
):
    try:
        result = service.adjust_stock(request.sku, request.quantity)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(request: ReservationCreateRequest, api_key: str = Depends(verify_api_key)):
    try:
        result = service.create_reservation(
            sku=request.sku,
            quantity=request.quantity,
            customer_id=request.customer_id,
            idempotency_key=request.idempotency_key,
        )
        return result
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    request: ReservationActionRequest,
    api_key: str = Depends(verify_api_key),
):
    try:
        result = service.confirm_reservation(reservation_id)
        return result
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", status_code=204)
async def cancel_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key),
):
    try:
        service.cancel_reservation(reservation_id)
        return None
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int):
    try:
        result = service.get_order(order_id)
        return result
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.get("/customers/{customer_id}/orders", response_model=OrderListResponse)
async def list_orders(
    customer_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    result = service.list_orders(customer_id, page, page_size)
    return result


@app.post("/maintenance/cleanup-expired", status_code=200)
async def cleanup_expired_reservations(api_key: str = Depends(verify_api_key)):
    count = service.cleanup_expired_reservations()
    return {"expired_count": count}
