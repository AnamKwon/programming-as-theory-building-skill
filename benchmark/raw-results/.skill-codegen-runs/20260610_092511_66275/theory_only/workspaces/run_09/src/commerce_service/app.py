import uvicorn
from fastapi import FastAPI, HTTPException, status, Depends, Query
from commerce_service.models import (
    CreateSkuRequest,
    SkuResponse,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderListResponse,
    ErrorResponse,
)
from commerce_service.repository import Repository
from commerce_service.service import (
    Service,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidReservationStateError,
    SkuNotFoundError,
)
from commerce_service.security import get_api_key_dependency

app = FastAPI(title="Commerce Service", version="0.1.0")
repo = Repository()
service = Service(repo)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SkuResponse, status_code=status.HTTP_201_CREATED)
def create_sku(
    request: CreateSkuRequest,
    api_key: str = Depends(get_api_key_dependency),
):
    return service.create_sku(request.name, request.total_stock)


@app.post("/skus/{sku_id}/adjust-stock", response_model=SkuResponse)
def adjust_stock(
    sku_id: int,
    request: AdjustStockRequest,
    api_key: str = Depends(get_api_key_dependency),
):
    try:
        return service.adjust_stock(sku_id, request.adjustment)
    except SkuNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(get_api_key_dependency),
):
    try:
        return service.create_reservation(request.sku_id, request.quantity, request.idempotency_key)
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
def confirm_reservation(
    reservation_id: int,
    api_key: str = Depends(get_api_key_dependency),
):
    try:
        return service.confirm_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except InvalidReservationStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: int,
    api_key: str = Depends(get_api_key_dependency),
):
    try:
        return service.cancel_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidReservationStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    limit: int = Query(10, gt=0, le=100),
    offset: int = Query(0, ge=0),
):
    return service.get_orders(limit, offset)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
