from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse

from .models import (
    ErrorResponse,
    OrderListResponse,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustment,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    SKUNotFoundError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

_repo = Repository()
_service = Service(_repo)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse)
async def create_sku(req: SKUCreate, _: str = Depends(verify_api_key)):
    try:
        return _service.create_sku(req.sku_id, req.name, req.total_stock)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: str,
    req: StockAdjustment,
    _: str = Depends(verify_api_key),
):
    try:
        return _service.adjust_stock(sku_id, req.quantity_change)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    req: ReservationCreate,
    _: str = Depends(verify_api_key),
):
    try:
        return _service.create_reservation(req.sku_id, req.quantity, req.idempotency_key)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
):
    try:
        return _service.confirm_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
):
    try:
        return _service.cancel_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    _: str = Depends(verify_api_key),
):
    try:
        orders, total = _service.get_orders(offset, limit)
        return OrderListResponse(orders=orders, total=total, offset=offset, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
