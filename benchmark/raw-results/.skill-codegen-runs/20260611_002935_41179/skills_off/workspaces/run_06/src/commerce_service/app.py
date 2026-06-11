"""FastAPI application setup and endpoints."""

from fastapi import FastAPI, Depends, HTTPException
from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    PaginatedOrdersResponse,
    HealthResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_token


app = FastAPI(title="Commerce Service API")

_repo: Repository = None
_service: CommerceService = None


def get_repository() -> Repository:
    """Get or create repository instance."""
    global _repo
    if _repo is None:
        _repo = Repository(db_path=":memory:")
    return _repo


def get_service() -> CommerceService:
    """Get or create service instance."""
    global _service
    if _service is None:
        _service = CommerceService(get_repository())
    return _service


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok")


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
) -> dict:
    """Create a new SKU with initial stock."""
    result = service.create_sku(request.sku, request.initial_stock)
    return result


@app.post("/stock/adjust", status_code=200)
async def adjust_stock(
    request: AdjustStockRequest,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
) -> dict:
    """Adjust stock level for a SKU."""
    try:
        result = service.adjust_stock(request.sku, request.amount)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
) -> ReservationResponse:
    """Create a stock reservation."""
    try:
        result = service.create_reservation(
            request.sku, request.quantity, request.idempotency_key
        )
        return result
    except ValueError as e:
        error_msg = str(e)
        if "Insufficient stock" in error_msg:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=error_msg)


@app.post("/reservations/{reservation_id}/confirm", status_code=200, response_model=ConfirmReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
) -> ConfirmReservationResponse:
    """Confirm a pending reservation and create an order."""
    try:
        result = service.confirm_reservation(reservation_id)
        return result
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        if "expired" in error_msg.lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        raise HTTPException(status_code=400, detail=error_msg)


@app.post("/reservations/{reservation_id}/cancel", status_code=200)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
) -> dict:
    """Cancel a reservation and restore stock."""
    try:
        result = service.cancel_reservation(reservation_id)
        return result
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)


@app.get("/orders", response_model=PaginatedOrdersResponse)
async def list_orders(
    page: int = 1,
    size: int = 10,
    service: CommerceService = Depends(get_service),
) -> PaginatedOrdersResponse:
    """List orders with pagination."""
    result = service.list_orders(page, size)
    return PaginatedOrdersResponse(
        items=result["items"],
        page=result["page"],
        size=result["size"],
        total=result["total"],
    )
