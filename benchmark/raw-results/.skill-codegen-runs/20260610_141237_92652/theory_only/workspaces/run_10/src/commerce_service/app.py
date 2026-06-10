from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from commerce_service.repository import get_db, Repository, init_db
from commerce_service.service import CommerceService
from commerce_service.security import verify_api_key
from commerce_service.models import (
    SKUCreate,
    SKUResponse,
    StockAdjustRequest,
    StockAdjustResponse,
    ReservationCreate,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
)

app = FastAPI()


@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201, response_model=SKUResponse)
async def create_sku(
    sku_data: SKUCreate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    try:
        repository = Repository(db)
        service = CommerceService(repository)
        result = service.create_sku(sku_data.sku, sku_data.initial_stock)
        return SKUResponse(sku=result.sku, available_stock=result.available_stock)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=StockAdjustResponse)
async def adjust_stock(
    request: StockAdjustRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    try:
        repository = Repository(db)
        service = CommerceService(repository)
        result = service.adjust_stock(request.sku, request.amount)
        return StockAdjustResponse(sku=result.sku, available_stock=result.available_stock)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(
    request: ReservationCreate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    try:
        repository = Repository(db)
        service = CommerceService(repository)
        result = service.create_reservation(request.sku, request.quantity, request.idempotency_key)
        return ReservationResponse(
            id=result.id,
            sku=result.sku,
            quantity=result.quantity,
            status=result.status,
            created_at=result.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    id: int,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    try:
        repository = Repository(db)
        service = CommerceService(repository)
        result = service.confirm_reservation(id)
        return OrderResponse(
            id=result.id,
            reservation_id=result.reservation_id,
            created_at=result.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    id: int,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    try:
        repository = Repository(db)
        service = CommerceService(repository)
        result = service.cancel_reservation(id)
        return ReservationResponse(
            id=result.id,
            sku=result.sku,
            quantity=result.quantity,
            status=result.status,
            created_at=result.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db),
):
    repository = Repository(db)
    service = CommerceService(repository)
    orders, total, page_num, size_num = service.list_orders(page, size)
    return OrderListResponse(
        items=[
            OrderResponse(
                id=o.id,
                reservation_id=o.reservation_id,
                created_at=o.created_at,
            )
            for o in orders
        ],
        page=page_num,
        size=size_num,
        total=total,
    )
