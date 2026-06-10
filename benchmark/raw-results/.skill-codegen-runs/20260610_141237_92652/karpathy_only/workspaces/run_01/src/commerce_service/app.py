from fastapi import Depends, FastAPI, HTTPException, Query, status

from commerce_service.models import (
    AdjustStockRequest,
    CreateReservationRequest,
    CreateSKURequest,
    HealthResponse,
    OrderListResponse,
    ReservationResponse,
    SKUResponse,
)
from commerce_service.repository import Repository
from commerce_service.security import verify_api_key
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    InvalidStateError,
    ReservationExpiredError,
    ReservationNotFoundError,
)

app = FastAPI(title="Commerce Service API", version="0.1.0")
repository = Repository("sqlite:///commerce.db")
service = CommerceService(repository)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_key),
):
    return service.create_sku(request)


@app.post("/stock/adjust", status_code=status.HTTP_200_OK)
async def adjust_stock(
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
):
    return service.adjust_stock(request.sku, request.amount)


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_key),
):
    try:
        return service.create_reservation(request)
    except InsufficientStockError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient stock",
        )


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
):
    try:
        return service.confirm_reservation(reservation_id)
    except ReservationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )
    except InvalidStateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ReservationExpiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation expired",
        )


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
):
    try:
        return service.cancel_reservation(reservation_id)
    except ReservationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )
    except InvalidStateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
):
    return service.get_orders(page, size)
