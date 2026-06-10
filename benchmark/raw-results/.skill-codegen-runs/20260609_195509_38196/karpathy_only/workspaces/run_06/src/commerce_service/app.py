from fastapi import FastAPI, HTTPException, Depends, status, Query
from fastapi.responses import JSONResponse

from .models import (
    SKURequest,
    SKUResponse,
    AdjustStockRequest,
    ReservationRequest,
    ReservationResponse,
    ConfirmReservationRequest,
    ConfirmReservationResponse,
    OrderResponse,
    OrderListResponse,
    ErrorResponse,
)
from .repository import Repository
from .service import (
    CommerceService,
    ReservationError,
    InsufficientStockError,
    ReservationNotFoundError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    DuplicateReservationError,
)
from .security import APIKeyValidator

app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
)

repo = Repository(db_path=":memory:")
service = CommerceService(repo)
api_key_validator = APIKeyValidator()


@app.get("/health")
async def health_check():
    """Service health check endpoint."""
    return {"status": "healthy"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: SKURequest,
    _: str = Depends(api_key_validator),
):
    """Create a new SKU with initial stock level."""
    try:
        result = service.create_sku(request.sku, request.stock)
        return result
    except ReservationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get("/skus/{sku_code}", response_model=SKUResponse)
async def get_sku(sku_code: str):
    """Get SKU details including available stock."""
    try:
        result = service.get_sku(sku_code)
        return result
    except ReservationError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@app.post("/skus/{sku_code}/adjust-stock", response_model=SKUResponse)
async def adjust_stock(
    sku_code: str,
    request: AdjustStockRequest,
    _: str = Depends(api_key_validator),
):
    """Adjust stock level for a SKU."""
    try:
        result = service.adjust_stock(sku_code, request.adjustment)
        return result
    except ReservationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: ReservationRequest,
    _: str = Depends(api_key_validator),
):
    """Create a new inventory reservation."""
    try:
        result = service.create_reservation(
            sku=request.sku,
            quantity=request.quantity,
            idempotency_key=request.idempotency_key,
            customer_id=request.customer_id,
        )
        return result
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ReservationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.patch("/reservations/{reservation_id}/confirm", response_model=ConfirmReservationResponse)
async def confirm_reservation(
    reservation_id: str,
    request: ConfirmReservationRequest,
    _: str = Depends(api_key_validator),
):
    """Confirm a pending reservation, converting it to an order."""
    try:
        result = service.confirm_reservation(
            reservation_id=reservation_id,
            idempotency_key=request.idempotency_key,
        )
        return result
    except ReservationExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e),
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ReservationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ReservationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.delete("/reservations/{reservation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_reservation(
    reservation_id: str,
    _: str = Depends(api_key_validator),
):
    """Cancel a pending reservation, releasing reserved stock."""
    try:
        service.cancel_reservation(reservation_id)
        return None
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ReservationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ReservationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """List orders with pagination."""
    result = service.list_orders(page=page, page_size=page_size)
    return result


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    """Handle unexpected exceptions."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )
