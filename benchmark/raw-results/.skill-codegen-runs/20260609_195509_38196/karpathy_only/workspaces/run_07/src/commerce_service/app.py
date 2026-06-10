from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session

from .models import (
    OrderResponse,
    PaginatedOrderResponse,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustment,
    init_db,
)
from .security import validate_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

SessionLocal = init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
def create_sku(req: SKUCreate, db: Session = Depends(get_db), _: str = Depends(validate_api_key)):
    service = CommerceService(db)
    sku = service.create_sku(name=req.name, initial_stock=req.current_stock)
    return SKUResponse(id=sku.id, name=sku.name, current_stock=sku.current_stock)


@app.patch("/skus/{sku_id}/stock", response_model=SKUResponse)
def adjust_stock(
    sku_id: str,
    req: StockAdjustment,
    db: Session = Depends(get_db),
    _: str = Depends(validate_api_key),
):
    service = CommerceService(db)
    try:
        sku = service.adjust_stock(sku_id, req.quantity_delta)
        return SKUResponse(id=sku.id, name=sku.name, current_stock=sku.current_stock)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(
    req: ReservationCreate,
    db: Session = Depends(get_db),
    _: str = Depends(validate_api_key),
):
    service = CommerceService(db)
    try:
        reservation = service.create_reservation(
            sku_id=req.sku_id,
            quantity=req.quantity,
            idempotency_key=req.idempotency_key,
        )
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
        )
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
def confirm_reservation(
    reservation_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(validate_api_key),
):
    service = CommerceService(db)
    try:
        order = service.confirm_reservation(reservation_id)
        return OrderResponse(
            id=order.id,
            reservation_id=order.reservation_id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            status=order.status,
            created_at=order.created_at,
        )
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(validate_api_key),
):
    service = CommerceService(db)
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
        )
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str, db: Session = Depends(get_db)):
    service = CommerceService(db)
    try:
        order = service.get_order(order_id)
        return OrderResponse(
            id=order.id,
            reservation_id=order.reservation_id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            status=order.status,
            created_at=order.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.get("/orders", response_model=PaginatedOrderResponse)
def list_orders(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    orders, total = service.list_orders(limit=limit, offset=offset)
    items = [
        OrderResponse(
            id=order.id,
            reservation_id=order.reservation_id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            status=order.status,
            created_at=order.created_at,
        )
        for order in orders
    ]
    next_cursor = None
    if offset + limit < total:
        next_cursor = str(offset + limit)
    return PaginatedOrderResponse(items=items, total=total, cursor=next_cursor)
