from fastapi import Depends, FastAPI, HTTPException, Query

from .models import (
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
    SKUNotFoundError,
)

app = FastAPI(title="Commerce Service", version="1.0.0")
repo = Repository()
service = CommerceService(repo)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/skus", response_model=SKUResponse)
async def create_sku(sku: SKUCreate, api_key: str = Depends(verify_api_key)):
    try:
        result = service.create_sku(sku.sku_code, sku.name)
        return SKUResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/{sku_id}/adjust")
async def adjust_stock(
    sku_id: int, adjustment: StockAdjustment, api_key: str = Depends(verify_api_key)
):
    try:
        result = service.adjust_stock(sku_id, adjustment.adjustment)
        return result
    except SKUNotFoundError:
        raise HTTPException(status_code=404, detail="SKU not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    req: ReservationCreate, api_key: str = Depends(verify_api_key)
):
    try:
        result = service.create_reservation(req.sku_id, req.quantity, req.idempotency_key)
        return ReservationResponse(**result)
    except SKUNotFoundError:
        raise HTTPException(status_code=404, detail="SKU not found")
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int, api_key: str = Depends(verify_api_key)
):
    try:
        result = service.confirm_reservation(reservation_id)
        return ReservationResponse(**result)
    except ReservationNotFoundError:
        raise HTTPException(status_code=404, detail="Reservation not found")
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int, api_key: str = Depends(verify_api_key)
):
    try:
        result = service.cancel_reservation(reservation_id)
        return ReservationResponse(**result)
    except ReservationNotFoundError:
        raise HTTPException(status_code=404, detail="Reservation not found")
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    api_key: str = Depends(verify_api_key),
):
    result = service.list_orders(limit=limit, offset=offset)
    return OrderListResponse(**result)
