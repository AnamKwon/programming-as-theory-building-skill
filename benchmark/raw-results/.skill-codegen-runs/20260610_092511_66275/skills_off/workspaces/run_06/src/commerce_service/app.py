from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session

from . import models
from .models import SessionLocal, engine
from .security import verify_api_key
from .service import CommerceService

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/skus", response_model=models.SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: models.SKURequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    try:
        service = CommerceService(db)
        sku = service.create_sku(request.id, request.name, float(request.price))
        return sku
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/skus/{sku_id}", response_model=models.SKUResponse)
async def get_sku(
    sku_id: str,
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    sku = service.skus.get(sku_id)
    if not sku:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found")
    return sku


@app.post("/stock/adjust", response_model=models.StockResponse)
async def adjust_stock(
    request: models.AdjustStockRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    try:
        service = CommerceService(db)
        stock = service.adjust_stock(request.sku_id, request.quantity)
        return stock
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=models.ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: models.CreateReservationRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    try:
        service = CommerceService(db)
        reservation = service.create_reservation(
            request.sku_id,
            request.quantity,
            request.idempotency_key,
        )
        return reservation
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=models.ReservationResponse)
async def confirm_reservation(
    reservation_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    try:
        service = CommerceService(db)
        reservation = service.confirm_reservation(reservation_id)
        return reservation
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=models.ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    try:
        service = CommerceService(db)
        reservation = service.cancel_reservation(reservation_id)
        return reservation
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders/{order_id}", response_model=models.OrderResponse)
async def get_order(
    order_id: str,
    db: Session = Depends(get_db),
):
    try:
        service = CommerceService(db)
        order = service.get_order(order_id)
        return order
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.get("/orders", response_model=models.OrderListResponse)
async def list_orders(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    orders, total = service.list_orders(limit, offset)
    return models.OrderListResponse(
        items=orders,
        total=total,
        limit=limit,
        offset=offset,
    )
