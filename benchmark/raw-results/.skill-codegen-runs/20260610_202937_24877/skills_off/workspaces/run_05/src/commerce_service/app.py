from fastapi import FastAPI, HTTPException, Depends
from .models import (
    CreateSKURequest,
    SKUResponse,
    AdjustStockRequest,
    StockResponse,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    PaginatedOrdersResponse,
)
from .service import CommerceService
from .security import verify_api_key

app = FastAPI()
service = CommerceService()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key),
):
    try:
        result = service.create_sku(request.sku, request.initial_stock)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=StockResponse)
async def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key),
):
    try:
        result = service.adjust_stock(request.sku, request.amount)
        if result is None:
            raise HTTPException(status_code=404, detail="SKU not found")
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key),
):
    try:
        result = service.create_reservation(
            request.sku, request.quantity, request.idempotency_key
        )
        return result
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: str,
    api_key: str = Depends(verify_api_key),
):
    try:
        result = service.confirm_reservation(reservation_id)
        return result
    except ValueError as e:
        if "Reservation expired" in str(e):
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "not PENDING" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: str,
    api_key: str = Depends(verify_api_key),
):
    try:
        result = service.cancel_reservation(reservation_id)
        return result
    except ValueError as e:
        if "not PENDING" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=PaginatedOrdersResponse)
async def get_orders(page: int = 1, size: int = 10):
    try:
        if page < 1:
            page = 1
        if size < 1:
            size = 10

        orders, total = service.get_orders(page, size)
        return {
            "items": orders,
            "page": page,
            "size": size,
            "total": total,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
