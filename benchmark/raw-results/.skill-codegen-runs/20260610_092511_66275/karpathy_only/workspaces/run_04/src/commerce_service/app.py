"""FastAPI application for the commerce service."""

from fastapi import Depends, FastAPI, HTTPException, Query, status

from commerce_service.models import (
    ErrorResponse,
    OrderListResponse,
    OrderResponse,
    ReservationRequest,
    ReservationResponse,
    SKURequest,
    SKUResponse,
    StockAdjustmentRequest,
)
from commerce_service.repository import Repository
from commerce_service.security import verify_api_key
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    InvalidStatusTransitionError,
    ReservationExpiredError,
)

app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
)

_service: CommerceService | None = None


def get_service() -> CommerceService:
    """Get the service instance."""
    global _service
    if _service is None:
        repo = Repository(db_path="commerce.db")
        _service = CommerceService(repo)
    return _service


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, tags=["SKUs"], status_code=201)
async def create_sku(
    request: SKURequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Create a new SKU with initial stock."""
    try:
        sku = service.create_sku(request.sku_id, request.initial_stock)
        return SKUResponse(
            sku_id=sku["sku_id"],
            stock=sku["stock"],
            created_at=sku["created_at"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/skus/{sku_id}/adjust-stock",
    response_model=SKUResponse,
    tags=["SKUs"],
)
async def adjust_stock(
    sku_id: str,
    request: StockAdjustmentRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Adjust stock level for a SKU."""
    try:
        sku = service.adjust_stock(sku_id, request.delta)
        return SKUResponse(
            sku_id=sku["sku_id"],
            stock=sku["stock"],
            created_at=sku["created_at"],
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post(
    "/reservations",
    response_model=ReservationResponse,
    tags=["Reservations"],
    status_code=201,
)
async def create_reservation(
    request: ReservationRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Create a reservation for a SKU."""
    try:
        reservation = service.create_reservation(
            request.sku_id, request.quantity, request.idempotency_key
        )
        return ReservationResponse(
            reservation_id=reservation["reservation_id"],
            sku_id=reservation["sku_id"],
            quantity=reservation["quantity"],
            status=reservation["status"],
            expires_at=reservation["expires_at"],
            created_at=reservation["created_at"],
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=dict,
    tags=["Reservations"],
)
async def confirm_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Confirm a reservation into an order."""
    try:
        result = service.confirm_reservation(reservation_id)
        reservation = result["reservation"]
        order = result["order"]
        return {
            "reservation": ReservationResponse(
                reservation_id=reservation["reservation_id"],
                sku_id=reservation["sku_id"],
                quantity=reservation["quantity"],
                status=reservation["status"],
                expires_at=reservation["expires_at"],
                created_at=reservation["created_at"],
            ),
            "order": OrderResponse(
                order_id=order["order_id"],
                sku_id=order["sku_id"],
                quantity=order["quantity"],
                status=order["status"],
                created_at=order["created_at"],
                completed_at=order["completed_at"],
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
    tags=["Reservations"],
)
async def cancel_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Cancel a reservation and return reserved stock."""
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(
            reservation_id=reservation["reservation_id"],
            sku_id=reservation["sku_id"],
            quantity=reservation["quantity"],
            status=reservation["status"],
            expires_at=reservation["expires_at"],
            created_at=reservation["created_at"],
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/orders", response_model=OrderListResponse, tags=["Orders"])
async def list_orders(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: CommerceService = Depends(get_service),
):
    """List orders with pagination."""
    orders, total = service.list_orders(limit, offset)
    return OrderListResponse(
        orders=[
            OrderResponse(
                order_id=order["order_id"],
                sku_id=order["sku_id"],
                quantity=order["quantity"],
                status=order["status"],
                created_at=order["created_at"],
                completed_at=order["completed_at"],
            )
            for order in orders
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    """Handle unexpected exceptions."""
    return {
        "error": "Internal server error",
        "detail": str(exc) if isinstance(exc, (ValueError, RuntimeError)) else None,
    }
