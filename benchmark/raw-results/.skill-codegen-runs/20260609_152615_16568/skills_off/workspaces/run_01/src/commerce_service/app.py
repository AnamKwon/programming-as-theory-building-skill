import uuid
from contextlib import contextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, CreateReservationRequest, CreateSKURequest, HealthResponse, AdjustStockRequest
from .repository import Repository
from .security import verify_api_key
from .service import (
    CommercialService,
    ConflictError,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    ServiceError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_repository(db: Session = Depends(get_db)) -> Repository:
    return Repository(db)


def get_service(repo: Repository = Depends(get_repository)) -> CommercialService:
    return CommercialService(repo)


@app.post("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(status="healthy")


@app.post("/skus")
async def create_sku(
    req: CreateSKURequest,
    _: str = Depends(verify_api_key),
    service: CommercialService = Depends(get_service),
):
    try:
        result = service.create_sku(req.id, req.name, req.description)
        return result
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=409, detail=f"SKU {req.id} already exists")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.patch("/stock/{sku_id}")
async def adjust_stock(
    sku_id: str,
    req: AdjustStockRequest,
    _: str = Depends(verify_api_key),
    service: CommercialService = Depends(get_service),
):
    try:
        result = service.adjust_stock(sku_id, req.quantity)
        return result
    except ServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/reservations")
async def create_reservation(
    req: CreateReservationRequest,
    _: str = Depends(verify_api_key),
    service: CommercialService = Depends(get_service),
):
    try:
        result = service.create_reservation(
            req.sku_id, req.quantity, req.idempotency_key, req.reservation_ttl_seconds
        )
        return result
    except InsufficientStockError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    service: CommercialService = Depends(get_service),
):
    try:
        result = service.confirm_reservation(reservation_id)
        return result
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    service: CommercialService = Depends(get_service),
):
    try:
        result = service.cancel_reservation(reservation_id)
        return result
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/orders")
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    service: CommercialService = Depends(get_service),
):
    try:
        result = service.list_orders(skip, limit)
        return result
    except ServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
