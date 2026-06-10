"""FastAPI application for commerce service."""

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse

from .models import (
    HealthResponse,
    OrderListResponse,
    OrderResponse,
    OrderStatus,
    ReservationRequest,
    ReservationResponse,
    ReservationStatus,
    SKURequest,
    SKUResponse,
    StockAdjustmentRequest,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationAlreadyConfirmedError,
    ReservationExpiredError,
    ReservationNotFoundError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

# Dependency injection
_repo = Repository()
_service = CommerceService(_repo)


def get_service() -> CommerceService:
    return _service


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy")


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(payload: SKURequest, _: str = Depends(verify_api_key), service: CommerceService = Depends(get_service)):
    """Create a new SKU."""
    try:
        sku_record = service.create_sku(payload.sku, payload.stock_qty)
        return SKUResponse(
            id=sku_record["id"],
            sku=sku_record["sku"],
            stock_qty=sku_record["stock_qty"],
            created_at=sku_record["created_at"],
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/skus/{sku_id}/stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: int,
    payload: StockAdjustmentRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Adjust stock for a SKU."""
    try:
        sku_record = _repo.get_sku_by_id(sku_id)
        if not sku_record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found")

        updated = service.adjust_stock(sku_record["sku"], payload.delta)
        return SKUResponse(
            id=updated["id"],
            sku=updated["sku"],
            stock_qty=updated["stock_qty"],
            created_at=updated["created_at"],
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    payload: ReservationRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Create a reservation (reserves stock)."""
    try:
        reservation = service.reserve_inventory(payload.sku, payload.qty, payload.idempotency_key)
        return ReservationResponse(
            id=reservation["id"],
            sku=reservation["sku"],
            qty=reservation["qty"],
            status=ReservationStatus(reservation["status"]),
            created_at=reservation["created_at"],
            expires_at=reservation["expires_at"],
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Confirm a reservation (creates order)."""
    try:
        order = service.confirm_reservation(reservation_id)
        return OrderResponse(
            id=order["id"],
            sku=order["sku"],
            qty=order["qty"],
            status=OrderStatus(order["status"]),
            created_at=order["created_at"],
        )
    except ReservationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except (ReservationAlreadyConfirmedError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Cancel a reservation (releases stock)."""
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(
            id=reservation["id"],
            sku=reservation["sku"],
            qty=reservation["qty"],
            status=ReservationStatus(reservation["status"]),
            created_at=reservation["created_at"],
            expires_at=reservation["expires_at"],
        )
    except ReservationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: CommerceService = Depends(get_service),
):
    """Get paginated list of orders."""
    try:
        result = service.get_orders(page, page_size)
        return OrderListResponse(
            items=[
                OrderResponse(
                    id=order["id"],
                    sku=order["sku"],
                    qty=order["qty"],
                    status=OrderStatus(order["status"]),
                    created_at=order["created_at"],
                )
                for order in result["items"]
            ],
            total=result["total"],
            page=result["page"],
            page_size=result["page_size"],
            total_pages=result["total_pages"],
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
