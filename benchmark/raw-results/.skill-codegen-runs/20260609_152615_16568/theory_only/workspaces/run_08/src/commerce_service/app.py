from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session, sessionmaker

from commerce_service.models import (
    OrderListResponse,
    OrderResponse,
    ReservationRequest,
    ReservationResponse,
    SKURequest,
    SKUResponse,
    StockAdjustmentRequest,
    get_engine,
)
from commerce_service.security import verify_api_key
from commerce_service.service import (
    IdempotencyError,
    InsufficientStockError,
    OrderNotFoundError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    SKUNotFoundError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

engine = get_engine()
SessionLocal = sessionmaker(bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse)
def create_sku(
    req: SKURequest,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = Service(db)
    sku = service.create_sku(req.id, req.name, req.initial_stock)
    return SKUResponse(
        id=sku.id,
        name=sku.name,
        stock_quantity=sku.stock_quantity,
        created_at=sku.created_at,
    )


@app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
def adjust_stock(
    sku_id: str,
    req: StockAdjustmentRequest,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = Service(db)
    try:
        sku = service.adjust_stock(sku_id, req.adjustment)
        return SKUResponse(
            id=sku.id,
            name=sku.name,
            stock_quantity=sku.stock_quantity,
            created_at=sku.created_at,
        )
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(
    req: ReservationRequest,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = Service(db)
    try:
        reservation = service.create_reservation(
            req.sku_id, req.quantity, req.idempotency_key
        )
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=reservation.status,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except IdempotencyError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
def confirm_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = Service(db)
    try:
        order = service.confirm_reservation(reservation_id)
        return OrderResponse(
            id=order.id,
            reservation_id=order.reservation_id,
            status=order.status,
            created_at=order.created_at,
        )
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.delete("/reservations/{reservation_id}")
def cancel_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = Service(db)
    try:
        service.cancel_reservation(reservation_id)
        return {"status": "cancelled"}
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be 1-100")
    if offset < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offset must be >= 0")

    service = Service(db)
    orders, total = service.list_orders(limit=limit, offset=offset)

    return OrderListResponse(
        orders=[
            OrderResponse(
                id=o.id,
                reservation_id=o.reservation_id,
                status=o.status,
                created_at=o.created_at,
            )
            for o in orders
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str, db: Session = Depends(get_db)):
    service = Service(db)
    try:
        order = service.get_order(order_id)
        return OrderResponse(
            id=order.id,
            reservation_id=order.reservation_id,
            status=order.status,
            created_at=order.created_at,
        )
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
