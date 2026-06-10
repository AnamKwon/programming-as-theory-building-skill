from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, HealthResponse, OrderListResponse, OrderResponse, ReservationCreate, ReservationResponse, SKUCreate, SKUResponse, StockAdjustment
from .security import verify_api_key
from .service import CommerceService


DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Commerce Service", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health_check():
    return {"status": "healthy"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
def create_sku(
    payload: SKUCreate,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    try:
        sku = service.create_sku(
            code=payload.code,
            price=payload.price,
            stock_quantity=payload.stock_quantity,
        )
        return sku
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/skus/{sku_id}/stock", response_model=SKUResponse)
def adjust_stock(
    sku_id: int,
    payload: StockAdjustment,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    try:
        sku = service.adjust_stock(sku_id, payload.quantity_delta)
        return sku
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(
    payload: ReservationCreate,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    try:
        reservation = service.create_reservation(
            sku_id=payload.sku_id,
            quantity=payload.quantity,
            customer_id=payload.customer_id,
            ttl_seconds=payload.ttl_seconds,
            idempotency_key=payload.idempotency_key,
        )
        return reservation
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    try:
        order = service.confirm_reservation(reservation_id)
        return order
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    try:
        reservation = service.cancel_reservation(reservation_id)
        return reservation
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    items, total = service.list_orders(offset=offset, limit=limit)
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
    }
