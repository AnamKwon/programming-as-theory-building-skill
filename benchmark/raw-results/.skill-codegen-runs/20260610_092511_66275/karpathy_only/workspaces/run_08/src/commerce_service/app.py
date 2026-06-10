from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status

from .models import (
    ErrorResponse,
    OrderListResponse,
    OrderResponse,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustment,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
)

app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
)

repository = Repository()
service = CommerceService(repository)


# ============================================================================
# Exception Handlers
# ============================================================================


@app.exception_handler(InsufficientStockError)
def insufficient_stock_handler(request, exc):
    return {"detail": str(exc), "error_code": "INSUFFICIENT_STOCK"}, 409


@app.exception_handler(ReservationNotFoundError)
def reservation_not_found_handler(request, exc):
    return {"detail": str(exc), "error_code": "NOT_FOUND"}, 404


@app.exception_handler(ReservationExpiredError)
def reservation_expired_handler(request, exc):
    return {"detail": str(exc), "error_code": "RESERVATION_EXPIRED"}, 410


@app.exception_handler(InvalidStateTransitionError)
def invalid_state_handler(request, exc):
    return {"detail": str(exc), "error_code": "INVALID_STATE"}, 409


@app.exception_handler(ValueError)
def value_error_handler(request, exc):
    return {"detail": str(exc), "error_code": "INVALID_REQUEST"}, 400


# ============================================================================
# Health Check
# ============================================================================


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy"}


# ============================================================================
# SKU Endpoints
# ============================================================================


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
def create_sku(payload: SKUCreate, api_key: str = Depends(verify_api_key)) -> SKUResponse:
    return service.create_sku(payload.id, payload.name, payload.initial_stock)


# ============================================================================
# Stock Adjustment
# ============================================================================


@app.post("/stock/adjust", response_model=SKUResponse)
def adjust_stock(payload: StockAdjustment, api_key: str = Depends(verify_api_key)) -> SKUResponse:
    return service.adjust_stock(payload.sku_id, payload.quantity)


# ============================================================================
# Reservation Endpoints
# ============================================================================


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(
    payload: ReservationCreate, api_key: str = Depends(verify_api_key)
) -> ReservationResponse:
    try:
        return service.reserve(payload.sku_id, payload.quantity, payload.idempotency_key)
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
def confirm_reservation(
    reservation_id: str, api_key: str = Depends(verify_api_key)
) -> ReservationResponse:
    try:
        return service.confirm_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: str, api_key: str = Depends(verify_api_key)
) -> ReservationResponse:
    try:
        return service.cancel_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ============================================================================
# Order Endpoints
# ============================================================================


@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
    api_key: str = Depends(verify_api_key),
) -> OrderListResponse:
    orders, total = repository.list_orders(page, page_size)
    items = [
        OrderResponse(
            id=order.id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            state=order.state,
            created_at=order.created_at,
            expires_at=order.expires_at,
            confirmed_at=order.confirmed_at,
        )
        for order in orders
    ]
    return OrderListResponse(items=items, total=total, page=page, page_size=page_size)
