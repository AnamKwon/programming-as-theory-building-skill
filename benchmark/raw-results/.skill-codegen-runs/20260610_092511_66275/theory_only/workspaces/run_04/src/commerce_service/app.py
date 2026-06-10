from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from .models import (
    AdjustStockRequest,
    OrderResponse,
    PaginatedOrdersResponse,
    ReservationRequest,
    ReservationResponse,
    SKURequest,
    SKUResponse,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationAlreadyCancelledError,
    ReservationAlreadyConfirmedError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SkuNotFoundError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

# Initialize repository and service (in-memory SQLite for demo; use file path in production)
_repo = Repository(db_path=":memory:")
_service = CommerceService(_repo)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse)
def create_sku(request: SKURequest, _: str = Depends(verify_api_key)):
    try:
        return _service.create_sku(request.sku_id, request.name, request.initial_stock)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.patch("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
def adjust_stock(sku_id: str, request: AdjustStockRequest, _: str = Depends(verify_api_key)):
    try:
        return _service.adjust_stock(sku_id, request.quantity_delta)
    except SkuNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
def create_reservation(request: ReservationRequest):
    try:
        return _service.create_reservation(
            request.customer_id, request.sku_id, request.quantity, request.idempotency_key
        )
    except SkuNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
def confirm_reservation(reservation_id: str, _: str = Depends(verify_api_key)):
    try:
        return _service.confirm_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ReservationAlreadyConfirmedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ReservationAlreadyCancelledError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(reservation_id: str, _: str = Depends(verify_api_key)):
    try:
        return _service.cancel_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationAlreadyCancelledError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ReservationAlreadyConfirmedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/create-order", response_model=OrderResponse)
def create_order_from_reservation(reservation_id: str, _: str = Depends(verify_api_key)):
    try:
        return _service.create_order_from_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=PaginatedOrdersResponse)
def list_orders(limit: int = 10, offset: int = 0, _: str = Depends(verify_api_key)):
    if limit < 1 or limit > 100:
        limit = 10
    if offset < 0:
        offset = 0
    orders, total = _service.list_orders(limit, offset)
    return PaginatedOrdersResponse(orders=orders, total=total, limit=limit, offset=offset)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
