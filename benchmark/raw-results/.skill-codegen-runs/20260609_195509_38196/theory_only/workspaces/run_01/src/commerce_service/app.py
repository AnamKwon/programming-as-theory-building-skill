from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .models import Base
from .repository import Repository
from .service import (
    CommerceService,
    InvalidStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    ReservationStatusError,
    IdempotencyError,
)
from .security import verify_api_key
from . import models

# ============================================================================
# Setup
# ============================================================================

DATABASE_URL = "sqlite:///commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    repo = Repository(db)
    return CommerceService(repo)


# ============================================================================
# Health & Status
# ============================================================================


@app.get("/health")
async def health():
    return {"status": "ok"}


# ============================================================================
# SKU Endpoints
# ============================================================================


@app.post("/skus", response_model=models.SKUResponse)
async def create_sku(
    req: models.CreateSKURequest,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    try:
        sku = service.create_sku(req.id, req.name, req.quantity_on_hand)
        return sku
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/skus/{sku_id}", response_model=models.SKUResponse)
async def get_sku(
    sku_id: str,
    service: CommerceService = Depends(get_service),
):
    try:
        sku = service.get_sku(sku_id)
        return sku
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/stock/adjust", response_model=models.SKUResponse)
async def adjust_stock(
    req: models.AdjustStockRequest,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    try:
        sku = service.adjust_stock(req.sku_id, req.delta)
        return sku
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStockError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Reservation Endpoints
# ============================================================================


@app.post("/reservations", response_model=models.ReservationResponse)
async def create_reservation(
    req: models.CreateReservationRequest,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    try:
        reservation = service.create_reservation(
            req.sku_id, req.quantity, req.idempotency_key
        )
        return reservation
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStockError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IdempotencyError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/reservations/{reservation_id}", response_model=models.ReservationResponse)
async def get_reservation(
    reservation_id: str,
    service: CommerceService = Depends(get_service),
):
    try:
        reservation = service.get_reservation(reservation_id)
        return reservation
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=models.OrderResponse)
async def confirm_reservation(
    reservation_id: str,
    req: models.ConfirmReservationRequest,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    try:
        order = service.confirm_reservation(reservation_id, req.idempotency_key)
        return order
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationStatusError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=models.ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return reservation
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationStatusError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ============================================================================
# Order Endpoints
# ============================================================================


@app.get("/orders", response_model=models.OrderListResponse)
async def list_orders(
    page: int = 1,
    page_size: int = 10,
    service: CommerceService = Depends(get_service),
):
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=400, detail="page_size must be between 1 and 100")

    orders, total = service.list_orders(page=page, page_size=page_size)
    has_next = (page * page_size) < total

    return models.OrderListResponse(
        orders=orders,
        total=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
    )


@app.get("/orders/{order_id}", response_model=models.OrderResponse)
async def get_order(
    order_id: str,
    service: CommerceService = Depends(get_service),
):
    try:
        order = service.get_order(order_id)
        return order
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
