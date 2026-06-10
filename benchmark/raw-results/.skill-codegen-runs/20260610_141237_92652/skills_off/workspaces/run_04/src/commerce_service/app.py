from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    ReservationRequest,
    ReservationResponse,
    SKURequest,
    StockAdjustRequest,
    get_db_engine,
    init_db,
)
from .security import verify_api_key
from .service import CommerceService

app = FastAPI(title="Commerce Inventory & Order API")

engine = get_db_engine()
init_db(engine)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
def create_sku(
    request: SKURequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    return service.create_sku(request.sku, request.initial_stock)


@app.post("/stock/adjust")
def adjust_stock(
    request: StockAdjustRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    return service.adjust_stock(request.sku, request.amount)


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
def create_reservation(
    request: ReservationRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    return service.create_reservation(request.sku, request.quantity, request.idempotency_key)


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
def confirm_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    return service.confirm_reservation(reservation_id)


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    return service.cancel_reservation(reservation_id)


@app.get("/orders")
def get_orders(
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    return service.get_orders(page=page, size=size)
