from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session

from .models import (
    Base,
    ErrorResponse,
    OrderListResponse,
    OrderResponse,
    ReservationCancel,
    ReservationConfirm,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustment,
    get_engine,
    get_session_factory,
)
from .security import verify_api_key
from .service import (
    CommerceService,
    IdempotencyError,
    InsufficientStockError,
    ReservationAlreadyConfirmedError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
    ServiceError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

engine = get_engine()
SessionLocal = get_session_factory(engine)

Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse)
async def create_sku(
    sku: SKUCreate, api_key: str = Depends(verify_api_key), db: Session = Depends(get_db)
):
    try:
        service = CommerceService(db)
        return service.create_sku(sku.id, sku.name, sku.available_stock)
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: str,
    adjustment: StockAdjustment,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    try:
        service = CommerceService(db)
        return service.adjust_stock(sku_id, adjustment.quantity_delta)
    except SKUNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SKU {sku_id} not found")
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    req: ReservationCreate,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    try:
        service = CommerceService(db)
        return service.create_reservation(req.sku_id, req.quantity, req.duration_minutes)
    except SKUNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SKU {req.sku_id} not found")
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=dict)
async def confirm_reservation(
    reservation_id: str,
    req: ReservationConfirm,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    try:
        service = CommerceService(db)
        reservation, order_id = service.confirm_reservation(
            reservation_id, req.idempotency_key
        )
        return {
            "reservation": reservation,
            "order_id": order_id,
        }
    except ReservationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Reservation {reservation_id} not found")
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ReservationAlreadyConfirmedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    req: ReservationCancel = ReservationCancel(),
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    try:
        service = CommerceService(db)
        return service.cancel_reservation(reservation_id)
    except ReservationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Reservation {reservation_id} not found")
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, gt=0, le=100),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    result = service.list_orders(skip, limit)
    return OrderListResponse(**result)


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, db: Session = Depends(get_db)):
    try:
        service = CommerceService(db)
        return service.get_order(order_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {order_id} not found")


@app.exception_handler(ServiceError)
async def service_error_handler(request, exc: ServiceError):
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
