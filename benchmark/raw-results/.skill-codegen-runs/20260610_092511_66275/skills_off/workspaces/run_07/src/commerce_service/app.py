from fastapi import FastAPI, Depends, status
from sqlalchemy.orm import Session

from commerce_service.models import (
    HealthResponse,
    SKUCreate,
    SKU,
    StockAdjustment,
    ReservationCreate,
    ReservationResponse,
    OrderResponse,
    OrderList,
    ErrorResponse,
)
from commerce_service.repository import init_db, get_db, Repository
from commerce_service.service import CommerceService
from commerce_service.security import verify_api_key

app = FastAPI(title="Commerce Service", version="0.1.0")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")


@app.post("/skus", response_model=SKU, status_code=status.HTTP_201_CREATED)
async def create_sku(
    payload: SKUCreate,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(Repository(db))
    return service.create_sku(payload.sku_code, payload.name, payload.stock_count)


@app.post("/stock/adjust", response_model=SKU, status_code=status.HTTP_200_OK)
async def adjust_stock(
    payload: StockAdjustment,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(Repository(db))
    return service.adjust_stock(payload.sku_id, payload.quantity_delta)


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    payload: ReservationCreate,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(Repository(db))
    return service.create_reservation(payload.sku_id, payload.quantity, payload.idempotency_key)


@app.post("/reservations/{reservation_id}/confirm", status_code=status.HTTP_200_OK)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(Repository(db))
    res, order = service.confirm_reservation(reservation_id)
    return {"reservation": res, "order": order}


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse, status_code=status.HTTP_200_OK)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(Repository(db))
    return service.cancel_reservation(reservation_id)


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    service = CommerceService(Repository(db))
    return service.get_order(order_id)


@app.get("/orders", response_model=OrderList)
async def list_orders(
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
):
    service = CommerceService(Repository(db))
    orders, total = service.list_orders(page, page_size)
    return OrderList(items=orders, total=total, page=page, page_size=page_size)
