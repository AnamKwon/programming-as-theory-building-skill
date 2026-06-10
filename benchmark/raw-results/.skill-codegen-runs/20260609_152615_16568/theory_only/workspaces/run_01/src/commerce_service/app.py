from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    HealthResponse,
    ErrorResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key

app = FastAPI(title="Commerce Service", version="0.1.0")

# Initialize shared repository and service
_repo = Repository(db_path=":memory:")
_service = CommerceService(_repo)

__all__ = ["app", "_repo", "_service"]


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="healthy", timestamp=datetime.utcnow())


@app.post("/skus", status_code=201)
def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key),
) -> dict:
    try:
        _service.create_sku(request.sku, request.initial_stock)
        return {"sku": request.sku, "initial_stock": request.initial_stock}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/inventory/{sku}/adjust", status_code=200)
def adjust_stock(
    sku: str,
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key),
) -> dict:
    try:
        _service.adjust_stock(sku, request.quantity)
        return {"sku": sku, "adjustment": request.quantity}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201)
def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key),
) -> dict:
    try:
        reservation = _service.create_reservation(
            request.sku, request.units, request.idempotency_key
        )
        return {
            "reservation_id": reservation.reservation_id,
            "sku": reservation.sku,
            "units": reservation.units,
            "state": reservation.state,
            "expires_at": reservation.expires_at.isoformat(),
            "created_at": reservation.created_at.isoformat(),
        }
    except ValueError as e:
        error_msg = str(e)
        if "Insufficient stock" in error_msg:
            raise HTTPException(status_code=409, detail=error_msg)
        elif "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        elif "Duplicate" in error_msg:
            raise HTTPException(status_code=409, detail=error_msg)
        else:
            raise HTTPException(status_code=400, detail=error_msg)


@app.get("/reservations/{reservation_id}", status_code=200)
def get_reservation(reservation_id: str) -> dict:
    try:
        reservation = _service.get_reservation(reservation_id)
        return {
            "reservation_id": reservation.reservation_id,
            "sku": reservation.sku,
            "units": reservation.units,
            "state": reservation.state,
            "expires_at": reservation.expires_at.isoformat(),
            "created_at": reservation.created_at.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", status_code=200)
def confirm_reservation(
    reservation_id: str,
    api_key: str = Depends(verify_api_key),
) -> dict:
    try:
        order = _service.confirm_reservation(reservation_id)
        return {
            "order_id": order.order_id,
            "sku": order.sku,
            "units": order.units,
            "created_at": order.created_at.isoformat(),
            "confirmed_at": order.confirmed_at.isoformat(),
        }
    except ValueError as e:
        error_msg = str(e)
        if "expired" in error_msg.lower():
            raise HTTPException(status_code=410, detail=error_msg)
        elif "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        else:
            raise HTTPException(status_code=400, detail=error_msg)


@app.post("/reservations/{reservation_id}/cancel", status_code=200)
def cancel_reservation(
    reservation_id: str,
    api_key: str = Depends(verify_api_key),
) -> dict:
    try:
        _service.cancel_reservation(reservation_id)
        return {"reservation_id": reservation_id, "state": "cancelled"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/orders", status_code=200)
def get_orders(limit: int = 10, offset: int = 0) -> dict:
    try:
        orders, total = _service.get_orders(limit, offset)
        return {
            "orders": [
                {
                    "order_id": o.order_id,
                    "sku": o.sku,
                    "units": o.units,
                    "created_at": o.created_at.isoformat(),
                    "confirmed_at": o.confirmed_at.isoformat(),
                }
                for o in orders
            ],
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.exception_handler(ValueError)
def value_error_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "code": "validation_error"},
    )
