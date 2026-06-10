from fastapi import FastAPI, HTTPException, Header, Query, status

from . import models
from .repository import Repository
from .security import get_api_key_from_header, validate_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    InvalidStateError,
    ReservationExpiredError,
)

app = FastAPI(title="Commerce Service")
repository = Repository()
service = CommerceService(repository)


@app.get("/health", response_model=models.HealthResponse)
def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201, response_model=dict)
def create_sku(
    request: models.SKUCreateRequest,
    api_key: str = Header(None, alias="X-API-Key"),
):
    validate_api_key(api_key)

    try:
        result = service.create_sku(request.sku, request.initial_stock)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", status_code=200, response_model=models.StockAdjustResponse)
def adjust_stock(
    request: models.StockAdjustRequest,
    api_key: str = Header(None, alias="X-API-Key"),
):
    validate_api_key(api_key)

    try:
        result = service.adjust_stock(request.sku, request.amount)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201, response_model=models.ReservationResponse)
def create_reservation(
    request: models.ReservationCreateRequest,
    api_key: str = Header(None, alias="X-API-Key"),
):
    validate_api_key(api_key)

    try:
        result = service.create_reservation(request.sku, request.quantity, request.idempotency_key)
        return result
    except InsufficientStockError:
        raise HTTPException(status_code=400, detail="Insufficient stock")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", status_code=200)
def confirm_reservation(
    reservation_id: int,
    api_key: str = Header(None, alias="X-API-Key"),
):
    validate_api_key(api_key)

    try:
        reservation_response, order_response = service.confirm_reservation(reservation_id)
        return {"reservation": reservation_response, "order": order_response}
    except ReservationExpiredError:
        raise HTTPException(status_code=400, detail="Reservation expired")
    except InvalidStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", status_code=200, response_model=models.ReservationResponse)
def cancel_reservation(
    reservation_id: int,
    api_key: str = Header(None, alias="X-API-Key"),
):
    validate_api_key(api_key)

    try:
        result = service.cancel_reservation(reservation_id)
        return result
    except InvalidStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", status_code=200, response_model=models.OrderListResponse)
def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
):
    orders, total = service.get_orders(page, size)
    return {
        "items": orders,
        "page": page,
        "size": size,
        "total": total,
    }
