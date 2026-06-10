"""FastAPI application."""

from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .models import (
    SessionLocal,
    init_db,
    SKUCreate,
    SKUResponse,
    StockAdjustment,
    ReservationCreate,
    ReservationResponse,
    OrderListResponse,
    OrderResponse,
)
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    InvalidStateTransitionError,
    IdempotencyViolationError,
)
from .security import verify_api_key

app = FastAPI(title="Commerce Service", version="0.1.0")

init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse)
async def create_sku(
    payload: SKUCreate,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    try:
        sku = service.create_sku(payload.name, payload.quantity_available)
        return sku
    except IntegrityError:
        raise HTTPException(status_code=409, detail="SKU name already exists")


@app.patch("/skus/{sku_id}/stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: int,
    payload: StockAdjustment,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    try:
        sku = service.adjust_stock(sku_id, payload.quantity_delta)
        return sku
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    payload: ReservationCreate,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    try:
        reservation = service.reserve_inventory(
            payload.sku_id, payload.quantity, payload.idempotency_key, payload.ttl_seconds
        )
        return reservation
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except IdempotencyViolationError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    try:
        reservation = service.confirm_reservation(reservation_id)
        return reservation
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    try:
        reservation = service.cancel_reservation(reservation_id)
        return reservation
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    orders, total = service.get_orders(limit, offset)
    return OrderListResponse(
        orders=[OrderResponse.model_validate(o) for o in orders],
        total=total,
        limit=limit,
        offset=offset,
    )
