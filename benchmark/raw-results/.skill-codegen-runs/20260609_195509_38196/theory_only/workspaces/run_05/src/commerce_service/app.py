from fastapi import Depends, FastAPI, HTTPException, Query, status

from .models import (
    AdjustStockRequest,
    CancelReservationRequest,
    ConfirmReservationRequest,
    CreateOrderRequest,
    CreateReservationRequest,
    CreateSKURequest,
    ErrorResponse,
    HealthResponse,
    OrderListResponse,
    OrderResponse,
    ReservationResponse,
    SKUResponse,
    StockResponse,
)
from .repository import Repository, get_session
from .security import verify_api_key
from .service import (
    InsufficientStockError,
    InvalidReservationStateError,
    OrderNotFoundError,
    ReservationAlreadyConfirmedError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    SKUNotFoundError,
)

app = FastAPI(title="Commerce Service", version="1.0.0")


def get_service(session=Depends(get_session)) -> Service:
    """Get service instance with repository dependency."""
    return Service(Repository(session))


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check service health."""
    return {"status": "healthy"}


@app.post("/skus", response_model=SKUResponse)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    """Create a new SKU."""
    try:
        sku = service.create_sku(request.sku_id, request.name, request.initial_stock)
        return SKUResponse(**sku)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/skus/{sku_id}/stock", response_model=StockResponse)
async def adjust_stock(
    sku_id: str,
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    """Adjust stock level for a SKU."""
    try:
        result = service.adjust_stock(sku_id, request.delta)
        return StockResponse(**result)
    except SKUNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    """Create a new reservation."""
    try:
        reservation = service.create_reservation(
            request.sku_id, request.quantity, request.idempotency_key
        )
        return ReservationResponse(**reservation)
    except SKUNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: str,
    request: ConfirmReservationRequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    """Confirm a pending reservation."""
    try:
        reservation = service.confirm_reservation(reservation_id, request.idempotency_key)
        return ReservationResponse(**reservation)
    except ReservationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ReservationExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e),
        )
    except (ReservationAlreadyConfirmedError, InvalidReservationStateError) as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    request: CancelReservationRequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    """Cancel a reservation."""
    try:
        reservation = service.cancel_reservation(reservation_id, request.idempotency_key)
        return ReservationResponse(**reservation)
    except ReservationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidReservationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/orders", response_model=OrderResponse)
async def create_order(
    request: CreateOrderRequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    """Create an order from a confirmed reservation."""
    try:
        order = service.create_order(request.reservation_id, request.idempotency_key)
        return OrderResponse(**order)
    except ReservationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidReservationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, service: Service = Depends(get_service)):
    """Get order details."""
    try:
        order = service.get_order(order_id)
        return OrderResponse(**order)
    except OrderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: Service = Depends(get_service),
):
    """List orders with pagination."""
    result = service.list_orders(limit=limit, offset=offset)
    return OrderListResponse(**result)
