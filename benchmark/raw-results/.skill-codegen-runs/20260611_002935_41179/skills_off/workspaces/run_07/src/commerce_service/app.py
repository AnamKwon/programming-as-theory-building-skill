"""FastAPI application for the commerce service."""

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse

from commerce_service.models import (
    SKURequest,
    SKUResponse,
    StockAdjustRequest,
    StockAdjustResponse,
    ReservationRequest,
    ReservationResponse,
    OrderListResponse,
    OrderResponse,
)
from commerce_service.security import verify_api_key
from commerce_service.service import SKUService, ReservationService, OrderService
from commerce_service.repository import init_db


app = FastAPI(title="Commerce Service", version="0.1.0")


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    init_db()


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: SKURequest,
    _: str = Depends(verify_api_key),
) -> SKUResponse:
    """Create a new SKU with initial stock."""
    service = SKUService()
    result = service.create_sku(request.sku, request.initial_stock)
    return SKUResponse(**result)


@app.post("/stock/adjust", status_code=200)
async def adjust_stock(
    request: StockAdjustRequest,
    _: str = Depends(verify_api_key),
) -> StockAdjustResponse:
    """Adjust stock level for a SKU."""
    service = SKUService()
    result = service.adjust_stock(request.sku, request.amount)
    if result is None:
        raise HTTPException(status_code=404, detail="SKU not found")
    return StockAdjustResponse(**result)


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: ReservationRequest,
    _: str = Depends(verify_api_key),
) -> ReservationResponse | dict:
    """Create a reservation for a SKU."""
    service = ReservationService()
    result, status_code = service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )

    if status_code == 400:
        raise HTTPException(status_code=400, detail=result["detail"])

    return JSONResponse(status_code=status_code, content=result)


@app.post("/reservations/{id}/confirm", status_code=200)
async def confirm_reservation(
    id: int,
    _: str = Depends(verify_api_key),
) -> OrderResponse | dict:
    """Confirm a reservation and create an order."""
    service = ReservationService()
    result, status_code = service.confirm_reservation(id)

    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=result.get("detail"))

    return JSONResponse(status_code=status_code, content=result)


@app.post("/reservations/{id}/cancel", status_code=200)
async def cancel_reservation(
    id: int,
    _: str = Depends(verify_api_key),
) -> ReservationResponse | dict:
    """Cancel a reservation and restore stock."""
    service = ReservationService()
    result, status_code = service.cancel_reservation(id)

    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=result.get("detail"))

    return JSONResponse(status_code=status_code, content=result)


@app.get("/orders", status_code=200)
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
) -> OrderListResponse:
    """Get paginated list of orders."""
    service = OrderService()
    result = service.get_orders(page, size)

    return OrderListResponse(
        orders=[OrderResponse(**order) for order in result["orders"]],
        total=result["total"],
        page=result["page"],
        size=result["size"],
        total_pages=result["total_pages"],
    )
