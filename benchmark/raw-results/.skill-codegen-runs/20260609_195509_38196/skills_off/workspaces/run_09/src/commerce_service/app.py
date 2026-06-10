from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session

from .models import (
    OrderListResponse,
    OrderResponse,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustment,
    init_db,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    CommercService,
    ReservationExpired,
    ReservationNotFound,
    SKUNotFound,
    StockUnavailable,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

SessionLocal = init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommercService:
    repo = Repository(db)
    return CommercService(repo)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse)
def create_sku(
    payload: SKUCreate,
    _: str = Depends(verify_api_key),
    service: CommercService = Depends(get_service),
):
    try:
        sku = service.create_sku(payload.sku_code, payload.initial_stock)
        return SKUResponse(
            id=sku.id,
            sku_code=sku.sku_code,
            current_stock=sku.current_stock,
            reserved_count=sku.reserved_count,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/skus/{sku_id}/stock", response_model=SKUResponse)
def adjust_stock(
    sku_id: int,
    payload: StockAdjustment,
    _: str = Depends(verify_api_key),
    service: CommercService = Depends(get_service),
):
    try:
        sku = service.adjust_stock(sku_id, payload.adjustment)
        return SKUResponse(
            id=sku.id,
            sku_code=sku.sku_code,
            current_stock=sku.current_stock,
            reserved_count=sku.reserved_count,
        )
    except SKUNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
def create_reservation(
    payload: ReservationCreate,
    _: str = Depends(verify_api_key),
    service: CommercService = Depends(get_service),
):
    try:
        reservation = service.reserve_inventory(
            payload.sku_id, payload.quantity, payload.idempotency_key, payload.ttl_seconds
        )
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=reservation.status,
            idempotency_key=reservation.idempotency_key,
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
        )
    except StockUnavailable as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except SKUNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=dict)
def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommercService = Depends(get_service),
):
    try:
        reservation, order = service.confirm_reservation(reservation_id)
        return {
            "reservation": ReservationResponse(
                id=reservation.id,
                sku_id=reservation.sku_id,
                quantity=reservation.quantity,
                status=reservation.status,
                idempotency_key=reservation.idempotency_key,
                created_at=reservation.created_at,
                expires_at=reservation.expires_at,
            ),
            "order": OrderResponse(
                id=order.id,
                sku_id=order.sku_id,
                quantity=order.quantity,
                status=order.status,
                reservation_id=order.reservation_id,
                created_at=order.created_at,
            ),
        }
    except ReservationNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpired as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommercService = Depends(get_service),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=reservation.status,
            idempotency_key=reservation.idempotency_key,
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
        )
    except ReservationNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, gt=0, le=100),
    service: CommercService = Depends(get_service),
):
    orders, total = service.list_orders(skip, limit)
    return OrderListResponse(
        total=total,
        skip=skip,
        limit=limit,
        orders=[
            OrderResponse(
                id=o.id,
                sku_id=o.sku_id,
                quantity=o.quantity,
                status=o.status,
                reservation_id=o.reservation_id,
                created_at=o.created_at,
            )
            for o in orders
        ],
    )
