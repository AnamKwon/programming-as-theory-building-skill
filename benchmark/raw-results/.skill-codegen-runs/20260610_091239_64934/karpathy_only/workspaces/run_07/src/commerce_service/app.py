from typing import Annotated

from fastapi import Depends, FastAPI, status
from sqlalchemy.orm import Session

from .models import (
    Base,
    OrderResponse,
    PaginatedOrderResponse,
    ReservationCreate,
    ReservationResponse,
    SessionLocal,
    SKUAdjustStock,
    SKUCreate,
    SKUResponse,
    engine,
)
from .security import verify_api_key
from .service import CommercService

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health", status_code=200)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    payload: SKUCreate,
    _: Annotated[str, Depends(verify_api_key)],
    db: Session = Depends(get_db),
):
    service = CommercService(db)
    sku = service.create_sku(payload.code, payload.quantity_available)
    return sku


@app.patch("/skus/{sku_id}/stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: int,
    payload: SKUAdjustStock,
    _: Annotated[str, Depends(verify_api_key)],
    db: Session = Depends(get_db),
):
    service = CommercService(db)
    sku = service.adjust_stock(sku_id, payload.adjustment)
    return sku


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    payload: ReservationCreate,
    _: Annotated[str, Depends(verify_api_key)],
    db: Session = Depends(get_db),
):
    service = CommercService(db)
    reservation = service.create_reservation(
        payload.sku_id, payload.quantity, payload.idempotency_key
    )
    return reservation


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    _: Annotated[str, Depends(verify_api_key)],
    db: Session = Depends(get_db),
):
    service = CommercService(db)
    reservation = service.confirm_reservation(reservation_id)
    return reservation


@app.delete("/reservations/{reservation_id}", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    _: Annotated[str, Depends(verify_api_key)],
    db: Session = Depends(get_db),
):
    service = CommercService(db)
    reservation = service.cancel_reservation(reservation_id)
    return reservation


@app.get("/orders", response_model=PaginatedOrderResponse)
async def get_orders(
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
):
    service = CommercService(db)
    orders, total, page, page_size, has_more = service.get_orders(page, page_size)
    return PaginatedOrderResponse(
        items=[OrderResponse.model_validate(o) for o in orders],
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )
