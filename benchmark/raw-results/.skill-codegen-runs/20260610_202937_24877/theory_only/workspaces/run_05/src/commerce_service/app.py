from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models import (
    Base,
    SKUCreate,
    StockAdjust,
    ReservationCreate,
    ReservationResponse,
    OrderResponse,
)
from .service import CommerceService
from .security import verify_api_key

DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    sku_data: SKUCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    result = service.create_sku(sku_data.sku, sku_data.initial_stock)
    return {"id": result.id, "sku": result.sku, "available_stock": result.available_stock}


@app.post("/stock/adjust", status_code=200)
async def adjust_stock(
    adjust_data: StockAdjust,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    result = service.adjust_stock(adjust_data.sku, adjust_data.amount)
    return {"sku": result.sku, "available_stock": result.available_stock}


@app.post("/reservations", status_code=201)
async def create_reservation(
    res_data: ReservationCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    result = service.create_reservation(
        res_data.sku, res_data.quantity, res_data.idempotency_key
    )
    return ReservationResponse(
        id=result.id,
        sku=result.sku,
        quantity=result.quantity,
        status=result.status,
        created_at=result.created_at,
    )


@app.post("/reservations/{id}/confirm", status_code=200)
async def confirm_reservation(
    id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    result = service.confirm_reservation(id)
    return ReservationResponse(
        id=result.id,
        sku=result.sku,
        quantity=result.quantity,
        status=result.status,
        created_at=result.created_at,
    )


@app.post("/reservations/{id}/cancel", status_code=200)
async def cancel_reservation(
    id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    result = service.cancel_reservation(id)
    return ReservationResponse(
        id=result.id,
        sku=result.sku,
        quantity=result.quantity,
        status=result.status,
        created_at=result.created_at,
    )


@app.get("/orders", status_code=200)
async def list_orders(
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    orders, total = service.get_orders(page, size)
    return {
        "items": [
            OrderResponse(
                id=order.id,
                reservation_id=order.reservation_id,
                sku=order.sku,
                quantity=order.quantity,
                created_at=order.created_at,
            )
            for order in orders
        ],
        "total": total,
        "page": page,
        "size": size,
    }
