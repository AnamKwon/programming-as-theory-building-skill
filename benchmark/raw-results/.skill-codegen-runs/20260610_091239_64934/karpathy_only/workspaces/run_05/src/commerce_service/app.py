import os

from fastapi import Depends, FastAPI, Query
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    Base,
    ErrorResponse,
    OrderListResponse,
    OrderResponse,
    ReservationCreateRequest,
    ReservationResponse,
    SKUCreateRequest,
    SKUResponse,
    StockAdjustmentRequest,
)
from .repository import Repository
from .security import api_key_header, verify_api_key
from .service import CommerceService

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
RESERVATION_TTL_MINUTES = int(os.getenv("RESERVATION_TTL_MINUTES", "15"))

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    repo = Repository(db)
    return CommerceService(repo, reservation_ttl_minutes=RESERVATION_TTL_MINUTES)


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, responses={409: {"model": ErrorResponse}})
async def create_sku(
    req: SKUCreateRequest,
    api_key: str | None = Depends(api_key_header),
    service: CommerceService = Depends(get_service),
) -> dict:
    verify_api_key(api_key)
    return service.create_sku(req.sku_id, req.name, req.total_stock)


@app.post("/skus/{sku_id}/stock", response_model=SKUResponse, responses={404: {"model": ErrorResponse}})
async def adjust_stock(
    sku_id: str,
    req: StockAdjustmentRequest,
    api_key: str | None = Depends(api_key_header),
    service: CommerceService = Depends(get_service),
) -> dict:
    verify_api_key(api_key)
    return service.adjust_stock(sku_id, req.adjustment)


@app.post(
    "/reservations",
    response_model=ReservationResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def create_reservation(
    req: ReservationCreateRequest,
    api_key: str | None = Depends(api_key_header),
    service: CommerceService = Depends(get_service),
) -> dict:
    verify_api_key(api_key)
    return service.create_reservation(req.sku_id, req.quantity, req.idempotency_key)


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=ReservationResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def confirm_reservation(
    reservation_id: str,
    api_key: str | None = Depends(api_key_header),
    service: CommerceService = Depends(get_service),
) -> dict:
    verify_api_key(api_key)
    return service.confirm_reservation(reservation_id)


@app.post(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def cancel_reservation(
    reservation_id: str,
    api_key: str | None = Depends(api_key_header),
    service: CommerceService = Depends(get_service),
) -> dict:
    verify_api_key(api_key)
    return service.cancel_reservation(reservation_id)


@app.get("/orders/{order_id}", response_model=OrderResponse, responses={404: {"model": ErrorResponse}})
async def get_order(
    order_id: str,
    service: CommerceService = Depends(get_service),
) -> dict:
    return service.get_order(order_id)


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: CommerceService = Depends(get_service),
) -> dict:
    return service.list_orders(limit, offset)
