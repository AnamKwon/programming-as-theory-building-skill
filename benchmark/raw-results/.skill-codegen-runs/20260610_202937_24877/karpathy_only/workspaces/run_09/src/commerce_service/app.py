from fastapi import Depends, FastAPI, HTTPException, Query, status

from .models import (
    HealthResponse,
    OrderListResponse,
    ReservationRequest,
    ReservationResponse,
    SKURequest,
    SKUResponse,
    StockAdjustRequest,
    StockAdjustResponse,
)
from .repository import Database, Repository
from .security import verify_api_key
from .service import (
    DuplicateIdempotencyKeyError,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    ReservationNotPendingError,
    Service,
    SKUNotFoundError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

db = Database(":memory:")
db.connect()
repo = Repository(db)
service = Service(repo)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    body: SKURequest, _: str = Depends(verify_api_key)
) -> SKUResponse:
    try:
        return service.create_sku(body.sku, body.initial_stock)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/stock/adjust", response_model=StockAdjustResponse)
async def adjust_stock(
    body: StockAdjustRequest, _: str = Depends(verify_api_key)
) -> StockAdjustResponse:
    try:
        return service.adjust_stock(body.sku, body.amount)
    except SKUNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SKU not found",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    body: ReservationRequest, _: str = Depends(verify_api_key)
) -> ReservationResponse:
    try:
        return service.create_reservation(body.sku, body.quantity, body.idempotency_key)
    except InsufficientStockError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient stock",
        )
    except SKUNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SKU not found",
        )
    except DuplicateIdempotencyKeyError as e:
        try:
            existing = repo.get_reservation_by_idempotency_key(body.idempotency_key)
            if existing:
                return service._reservation_to_response(existing)
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency key already exists",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations/{id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    id: int, _: str = Depends(verify_api_key)
) -> ReservationResponse:
    try:
        return service.confirm_reservation(id)
    except ReservationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )
    except ReservationNotPendingError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation is not in PENDING state",
        )
    except ReservationExpiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation expired",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations/{id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    id: int, _: str = Depends(verify_api_key)
) -> ReservationResponse:
    try:
        return service.cancel_reservation(id)
    except ReservationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )
    except ReservationNotPendingError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation is not in PENDING state",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
) -> OrderListResponse:
    return service.get_orders(page, size)
