from fastapi import FastAPI, HTTPException, Depends, Query
from typing import Annotated

from .models import (
    SKURequest, SKUResponse,
    StockAdjustRequest, StockAdjustResponse,
    ReservationRequest, ReservationResponse,
    OrderResponse, OrderListResponse
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key

app = FastAPI(title="Commerce Service")

# Global service instance
repo = Repository()
service = CommerceService(repo)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    request: SKURequest,
    api_key: Annotated[str, Depends(verify_api_key)]
):
    try:
        result = service.create_sku(request.sku, request.initial_stock)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=StockAdjustResponse)
async def adjust_stock(
    request: StockAdjustRequest,
    api_key: Annotated[str, Depends(verify_api_key)]
):
    try:
        result = service.adjust_stock(request.sku, request.amount)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: ReservationRequest,
    api_key: Annotated[str, Depends(verify_api_key)]
):
    try:
        result = service.create_reservation(request.sku, request.quantity, request.idempotency_key)
        return result
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: int,
    api_key: Annotated[str, Depends(verify_api_key)]
):
    try:
        result = service.confirm_reservation(reservation_id)
        return result
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "not PENDING" in str(e):
            raise HTTPException(status_code=400, detail="Reservation is not PENDING")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=dict)
async def cancel_reservation(
    reservation_id: int,
    api_key: Annotated[str, Depends(verify_api_key)]
):
    try:
        result = service.cancel_reservation(reservation_id)
        return result
    except ValueError as e:
        if "not PENDING" in str(e):
            raise HTTPException(status_code=400, detail="Reservation is not PENDING")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1)] = 10
):
    orders, total = service.get_orders(page, size)
    return {
        "items": orders,
        "page": page,
        "size": size,
        "total": total
    }
