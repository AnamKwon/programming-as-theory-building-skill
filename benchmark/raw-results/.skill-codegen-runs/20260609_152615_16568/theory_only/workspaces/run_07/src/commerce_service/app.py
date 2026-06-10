from fastapi import FastAPI, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from .models import (
    init_db,
    CreateSKURequest,
    SKUResponse,
    StockAdjustmentRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
)
from .repository import Repository
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidReservationStatusError,
    SKUNotFoundError,
)
from .security import verify_api_key

# Initialize database
engine, db_session = init_db()

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db() -> Session:
    """Dependency injection for database session."""
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    """Dependency injection for commerce service."""
    repo = Repository(db)
    return CommerceService(repo)


# ─── Public Endpoints ────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# ─── SKU Management ─────────────────────────────────────────────────────────

@app.post("/skus", response_model=SKUResponse, tags=["skus"])
async def create_sku(
    req: CreateSKURequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Create a new SKU with initial stock."""
    try:
        sku = service.create_sku(req.name, req.initial_stock)
        return SKUResponse(**sku)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/skus/{sku_id}/stock", response_model=SKUResponse, tags=["skus"])
async def adjust_stock(
    sku_id: int,
    req: StockAdjustmentRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Adjust stock level for a SKU."""
    try:
        sku = service.adjust_stock(sku_id, req.adjustment)
        return SKUResponse(**sku)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Reservation Management ─────────────────────────────────────────────────

@app.post("/reservations", response_model=ReservationResponse, tags=["reservations"])
async def create_reservation(
    req: CreateReservationRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Create a reservation for a SKU quantity.

    Supports idempotency via idempotency_key. If the same key is retried,
    returns the existing pending reservation without re-checking stock.
    """
    try:
        reservation = service.create_reservation(
            req.sku_id,
            req.quantity,
            req.idempotency_key,
        )
        return ReservationResponse(**reservation)
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except SKUNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse, tags=["reservations"])
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Confirm a pending reservation and create an order.

    Validates that reservation exists, is pending, and hasn't expired.
    """
    try:
        order = service.confirm_reservation(reservation_id)
        return OrderResponse(**order)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except InvalidReservationStatusError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse, tags=["reservations"])
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Cancel a reservation and release the stock hold."""
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(**reservation)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidReservationStatusError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Order Lookup ───────────────────────────────────────────────────────────

@app.get("/orders", response_model=OrderListResponse, tags=["orders"])
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    service: CommerceService = Depends(get_service),
):
    """List orders with pagination."""
    result = service.list_orders(skip=skip, limit=limit)
    return OrderListResponse(**result)
