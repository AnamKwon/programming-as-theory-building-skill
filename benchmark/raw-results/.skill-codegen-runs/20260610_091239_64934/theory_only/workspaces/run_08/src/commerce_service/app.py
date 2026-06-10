from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, status, Depends
from sqlalchemy.orm import Session
from commerce_service.models import (
    SKURequest,
    SKUResponse,
    StockAdjustRequest,
    StockResponse,
    ReservationCreateRequest,
    ReservationResponse,
    ReservationConfirmRequest,
    OrderResponse,
    OrderListResponse,
    HealthResponse,
)
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.service import (
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)
from commerce_service.security import verify_api_key

app = FastAPI(title="Commerce Service", version="0.1.0")
repo = Repository()
service = CommerceService(repo)


def get_db() -> Session:
    db = repo.get_session()
    try:
        yield db
    finally:
        db.close()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok", timestamp=datetime.utcnow())


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    req: SKURequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    try:
        result = service.create_sku(db, req.sku_id, req.name)
        return SKUResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/skus/{sku_id}", response_model=SKUResponse)
async def get_sku(sku_id: str, db: Session = Depends(get_db)):
    try:
        result = service.get_sku(db, sku_id)
        return SKUResponse(**result)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/stock/{sku_id}/adjust", response_model=StockResponse)
async def adjust_stock(
    sku_id: str,
    req: StockAdjustRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    try:
        result = service.adjust_stock(db, sku_id, req.quantity)
        return StockResponse(**result)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/stock/{sku_id}", response_model=StockResponse)
async def get_stock(sku_id: str, db: Session = Depends(get_db)):
    try:
        result = service.get_stock(db, sku_id)
        return StockResponse(**result)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    req: ReservationCreateRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    try:
        result = service.create_reservation(db, req.sku_id, req.quantity, req.idempotency_key)
        return ReservationResponse(**result)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: str,
    req: ReservationConfirmRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    try:
        result = service.confirm_reservation(db, reservation_id, req.idempotency_key)
        return OrderResponse(**result)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    try:
        result = service.cancel_reservation(db, reservation_id)
        return ReservationResponse(**result)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    limit: int = 10,
    cursor: Optional[str] = None,
    db: Session = Depends(get_db),
):
    result = service.list_orders(db, limit, cursor)
    return OrderListResponse(**result)


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, db: Session = Depends(get_db)):
    try:
        result = service.get_order(db, order_id)
        return OrderResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
