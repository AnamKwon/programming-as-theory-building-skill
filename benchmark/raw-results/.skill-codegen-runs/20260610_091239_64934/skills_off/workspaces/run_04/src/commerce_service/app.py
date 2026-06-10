"""FastAPI application."""
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from commerce_service import __version__
from commerce_service.models import (
    HealthResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustment,
    ReservationCreate,
    ReservationResponse,
    OrderListResponse,
    OrderResponse,
)
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    ServiceError,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    SKUNotFoundError,
)
from commerce_service.security import verify_api_key

app = FastAPI(title="Commerce Service", version=__version__)
repository = Repository()
service = CommerceService(repository)


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint."""
    return HealthResponse(status="ok", version=__version__)


@app.post("/skus", response_model=SKUResponse, status_code=201)
def create_sku(payload: SKUCreate, api_key: str = Depends(verify_api_key)):
    """Create a new SKU."""
    try:
        return service.create_sku(payload.sku_code, payload.name)
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", status_code=200)
def adjust_stock(payload: StockAdjustment, api_key: str = Depends(verify_api_key)):
    """Adjust stock level for a SKU."""
    try:
        return service.adjust_stock(payload.sku_code, payload.delta)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
def create_reservation(payload: ReservationCreate, api_key: str = Depends(verify_api_key)):
    """Create a reservation with idempotency."""
    try:
        return service.create_reservation(
            payload.sku_code, payload.quantity, payload.idempotency_key
        )
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (SKUNotFoundError, ReservationExpiredError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
def confirm_reservation(reservation_id: int, api_key: str = Depends(verify_api_key)):
    """Confirm a reservation and create an order."""
    try:
        return service.confirm_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", status_code=200)
def cancel_reservation(reservation_id: int, api_key: str = Depends(verify_api_key)):
    """Cancel a reservation."""
    try:
        return service.cancel_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    """List orders with pagination."""
    try:
        result = service.list_orders(offset, limit)
        return OrderListResponse(
            orders=result["orders"],
            total=result["total"],
            offset=result["offset"],
            limit=result["limit"],
        )
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: int):
    """Get a specific order by ID."""
    try:
        return service.get_order(order_id)
    except ServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
