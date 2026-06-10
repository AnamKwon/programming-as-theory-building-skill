from fastapi import FastAPI, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from .repository import init_db, SessionLocal
from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    HealthResponse,
)
from .security import get_api_key
from .service import CommerceService
from .repository import Repository

app = FastAPI(title="Commerce Service")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_repository(db: Session = Depends(get_db)) -> Repository:
    return Repository(db)


def get_service(repo: Repository = Depends(get_repository)) -> CommerceService:
    return CommerceService(repo)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(get_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        sku = service.create_sku(request.sku, request.initial_stock)
        return {
            "id": sku.id,
            "sku": sku.sku,
            "available_stock": sku.available_stock,
            "reserved_stock": sku.reserved_stock,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", status_code=200)
async def adjust_stock(
    request: AdjustStockRequest,
    _: str = Depends(get_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        sku = service.adjust_stock(request.sku, request.amount)
        return {
            "sku": sku.sku,
            "available_stock": sku.available_stock,
            "reserved_stock": sku.reserved_stock,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(get_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        reservation = service.create_reservation(
            request.sku, request.quantity, request.idempotency_key
        )
        return ReservationResponse.model_validate(reservation)
    except ValueError as e:
        error_msg = str(e)
        if "Insufficient stock" in error_msg:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=error_msg)


@app.post("/reservations/{reservation_id}/confirm", status_code=200)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(get_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        reservation, order = service.confirm_reservation(reservation_id)
        return {
            "reservation": ReservationResponse.model_validate(reservation),
            "order": OrderResponse.model_validate(order),
        }
    except ValueError as e:
        error_msg = str(e)
        if "expired" in error_msg.lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        raise HTTPException(status_code=400, detail=error_msg)


@app.post("/reservations/{reservation_id}/cancel", status_code=200)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(get_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse.model_validate(reservation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=dict)
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    _: str = Depends(get_api_key),
    service: CommerceService = Depends(get_service),
):
    orders, total = service.repo.get_orders(page, size)
    return {
        "orders": [OrderResponse.model_validate(order) for order in orders],
        "page": page,
        "size": size,
        "total": total,
    }
