from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    Base,
    OrderListResponse,
    OrderResponse,
    ReservationCreateRequest,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustmentRequest,
)
from .security import verify_api_key
from .service import CommerceService

DATABASE_URL = "sqlite:///commerce.db"
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


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(sku: SKUCreate, db: Session = Depends(get_db), _: str = Depends(verify_api_key)) -> SKUResponse:
    service = CommerceService(db)
    try:
        return service.create_sku(code=sku.code, name=sku.name, initial_stock=sku.initial_stock)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"SKU with code '{sku.code}' already exists")


@app.get("/skus/{sku_id}", response_model=SKUResponse)
async def get_sku(sku_id: int, db: Session = Depends(get_db)) -> SKUResponse:
    service = CommerceService(db)
    sku = service.get_sku(sku_id)
    if not sku:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found")
    return sku


@app.post("/stock/adjust", response_model=SKUResponse)
async def adjust_stock(
    request: StockAdjustmentRequest, db: Session = Depends(get_db), _: str = Depends(verify_api_key)
) -> SKUResponse:
    service = CommerceService(db)
    try:
        return service.adjust_stock(sku_id=request.sku_id, quantity_change=request.quantity_change)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: ReservationCreateRequest, db: Session = Depends(get_db), _: str = Depends(verify_api_key)
) -> ReservationResponse:
    service = CommerceService(db)
    try:
        return service.create_reservation(
            sku_id=request.sku_id,
            quantity=request.quantity,
            idempotency_key=request.idempotency_key,
            ttl_seconds=request.ttl_seconds,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int, db: Session = Depends(get_db), _: str = Depends(verify_api_key)
) -> ReservationResponse:
    service = CommerceService(db)
    try:
        return service.confirm_reservation(reservation_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int, db: Session = Depends(get_db), _: str = Depends(verify_api_key)
) -> ReservationResponse:
    service = CommerceService(db)
    try:
        return service.cancel_reservation(reservation_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(limit: int = 20, offset: int = 0, db: Session = Depends(get_db)) -> OrderListResponse:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Offset must be non-negative")

    service = CommerceService(db)
    items, total = service.order_repo.list_paginated(limit=limit, offset=offset)
    return OrderListResponse(
        total=total, limit=limit, offset=offset, items=[OrderResponse.model_validate(item) for item in items]
    )
