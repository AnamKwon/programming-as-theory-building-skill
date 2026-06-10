"""FastAPI application and route handlers."""
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import JSONResponse

from .models import (
    SKUSchema,
    SKUResponse,
    StockAdjustmentRequest,
    ReservationRequest,
    ReservationResponse,
    OrderResponse,
    PaginatedOrderResponse,
)
from .repository import Repository
from .service import (
    Service,
    ServiceError,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidStateTransitionError,
)
from .security import get_api_key


app = FastAPI(title="Commerce Service", version="0.1.0")

repo = Repository()
service = Service(repo)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/skus", response_model=SKUResponse)
async def create_sku(
    sku_data: SKUSchema,
    _api_key: str = Depends(get_api_key),
):
    """Create a new SKU."""
    try:
        result = service.create_sku(sku_data.sku, sku_data.name)
        return result
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/skus/{sku_id}/stock")
async def adjust_stock(
    sku_id: str,
    request: StockAdjustmentRequest,
    _api_key: str = Depends(get_api_key),
):
    """Adjust stock level for a SKU."""
    try:
        result = service.adjust_stock(sku_id, request.adjustment)
        return result
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    request: ReservationRequest,
    _api_key: str = Depends(get_api_key),
):
    """Create a reservation for inventory."""
    try:
        result = service.reserve(request.sku_id, request.quantity, request.idempotency_key)
        return result
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: int,
    _api_key: str = Depends(get_api_key),
):
    """Confirm a pending reservation."""
    try:
        result = service.confirm_reservation(reservation_id)
        return result
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except (ReservationNotFoundError, InvalidStateTransitionError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int,
    _api_key: str = Depends(get_api_key),
):
    """Cancel a pending reservation."""
    try:
        result = service.cancel_reservation(reservation_id)
        return result
    except (ReservationNotFoundError, InvalidStateTransitionError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=PaginatedOrderResponse)
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    _api_key: str = Depends(get_api_key),
):
    """List orders with pagination."""
    result = service.lookup_orders(page=page, page_size=page_size)
    return result
