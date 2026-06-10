from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session

from .models import (
    AdjustStockRequest,
    OrderListResponse,
    OrderResponse,
    ReservationCancelRequest,
    ReservationConfirmRequest,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    create_db_engine,
    create_session_factory,
)
from .security import verify_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
)

engine = create_db_engine()
SessionLocal = create_session_factory(engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: SKUCreate,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    try:
        sku = CommerceService(db).create_sku(request.id, request.name, request.initial_stock)
        return SKUResponse(
            id=sku.id,
            name=sku.name,
            available_stock=sku.available_stock,
            reserved_stock=sku.reserved_stock,
            created_at=sku.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: str,
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    try:
        sku = CommerceService(db).adjust_stock(sku_id, request.quantity)
        return SKUResponse(
            id=sku.id,
            name=sku.name,
            available_stock=sku.available_stock,
            reserved_stock=sku.reserved_stock,
            created_at=sku.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: ReservationCreate,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    try:
        reservation = service.create_reservation(
            request.sku_id,
            request.quantity,
            request.idempotency_key,
        )
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
            confirmed_at=reservation.confirmed_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: str,
    _request: ReservationConfirmRequest = None,
    __: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    try:
        order = service.confirm_reservation(reservation_id)
        return OrderResponse(
            id=order.id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            status=order.status,
            reservation_id=order.reservation_id,
            idempotency_key=order.idempotency_key,
            created_at=order.created_at,
            confirmed_at=order.confirmed_at,
        )
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    _request: ReservationCancelRequest = None,
    __: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
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
            confirmed_at=reservation.confirmed_at,
        )
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, db: Session = Depends(get_db)):
    service = CommerceService(db)
    try:
        order = service.get_order(order_id)
        return OrderResponse(
            id=order.id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            status=order.status,
            reservation_id=order.reservation_id,
            idempotency_key=order.idempotency_key,
            created_at=order.created_at,
            confirmed_at=order.confirmed_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(offset: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    service = CommerceService(db)
    orders, total = service.list_orders(offset, limit)
    return OrderListResponse(
        orders=[
            OrderResponse(
                id=order.id,
                sku_id=order.sku_id,
                quantity=order.quantity,
                status=order.status,
                reservation_id=order.reservation_id,
                idempotency_key=order.idempotency_key,
                created_at=order.created_at,
                confirmed_at=order.confirmed_at,
            )
            for order in orders
        ],
        total=total,
        offset=offset,
        limit=limit,
    )
