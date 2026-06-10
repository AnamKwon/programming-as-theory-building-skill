"""FastAPI application and endpoint definitions."""

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse

from commerce_service import __version__
from commerce_service.models import (
    AdjustStockRequest,
    CancelReservationRequest,
    ConfirmReservationRequest,
    CreateReservationRequest,
    CreateSKURequest,
    HealthResponse,
    OrderDetailResponse,
    PaginationParams,
    ReservationResponse,
    ReservationStatus,
)
from commerce_service.repository import Repository
from commerce_service.security import verify_api_key
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationAlreadyExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)

app = FastAPI(title="Commerce Service", version=__version__)

# Dependency injection
_repo = Repository(db_path="commerce.db")
_service = CommerceService(_repo)


def get_repository() -> Repository:
    return _repo


def get_service() -> CommerceService:
    return _service


# Health check (no auth required)
@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", version=__version__)


# SKU endpoints
@app.post("/skus", status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Create a new SKU."""
    try:
        result = service.create_sku(request.sku_id, request.name)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e


# Stock adjustment
@app.post("/stock/adjust", status_code=status.HTTP_200_OK)
async def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Adjust stock level for a SKU."""
    try:
        result = service.adjust_stock(request.sku_id, request.adjustment)
        return result
    except SKUNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e


# Reservation endpoints
@app.post("/reservations", status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Create a new reservation."""
    try:
        result = service.create_reservation(
            request.order_id,
            request.sku_id,
            request.quantity,
            request.idempotency_key,
        )
        return result
    except SKUNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found"
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e)
        ) from e
    except ReservationAlreadyExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e


@app.post("/reservations/{reservation_id}/confirm", status_code=status.HTTP_200_OK)
async def confirm_reservation(
    reservation_id: str,
    request: ConfirmReservationRequest,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Confirm a pending reservation."""
    try:
        result = service.confirm_reservation(reservation_id)
        return result
    except ReservationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found"
        )
    except ReservationAlreadyExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e


@app.post("/reservations/{reservation_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_reservation(
    reservation_id: str,
    request: CancelReservationRequest,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Cancel a reservation and release stock."""
    try:
        result = service.cancel_reservation(reservation_id)
        return result
    except ReservationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e


# Order endpoints
@app.get("/orders/{order_id}", response_model=OrderDetailResponse)
async def get_order(
    order_id: str,
    service: CommerceService = Depends(get_service),
):
    """Get order details with reservations."""
    order = service.get_order(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    return order


@app.get("/orders")
async def list_orders(
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    service: CommerceService = Depends(get_service),
):
    """List orders with pagination."""
    result = service.list_orders(offset, limit)
    return result


# Error handler
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )
