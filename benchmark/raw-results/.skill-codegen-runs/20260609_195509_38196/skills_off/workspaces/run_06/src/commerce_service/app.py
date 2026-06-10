from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, status

from commerce_service.models import (
    ErrorResponse,
    OrderListResponse,
    OrderResponse,
    ReservationActionResponse,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustment,
)
from commerce_service.repository import init_db
from commerce_service.security import verify_api_key
from commerce_service.service import (
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    SKUNotFoundError,
)


app = FastAPI(title="Commerce Service", version="0.1.0")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, dependencies=[Depends(verify_api_key)])
def create_sku(payload: SKUCreate):
    try:
        sku = Service.create_sku(payload.code, payload.name, payload.initial_stock)
        return SKUResponse(**sku)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )


@app.post(
    "/skus/{sku_id}/stock/adjust",
    response_model=SKUResponse,
    dependencies=[Depends(verify_api_key)],
)
def adjust_stock(sku_id: int, payload: StockAdjustment):
    try:
        sku = Service.adjust_stock(sku_id, payload.quantity)
        return SKUResponse(**sku)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post(
    "/reservations",
    response_model=ReservationResponse,
    dependencies=[Depends(verify_api_key)],
)
def create_reservation(payload: ReservationCreate):
    try:
        reservation = Service.create_reservation(
            payload.sku_id,
            payload.quantity,
            payload.idempotency_key,
            payload.ttl_seconds,
        )
        return _to_reservation_response(reservation)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=ReservationActionResponse,
    dependencies=[Depends(verify_api_key)],
)
def confirm_reservation(reservation_id: int):
    try:
        reservation, order_id = Service.confirm_reservation(reservation_id)
        return ReservationActionResponse(
            reservation_id=reservation["id"],
            order_id=order_id,
            status=reservation["status"],
            message="Reservation confirmed and order created",
        )
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationActionResponse,
    dependencies=[Depends(verify_api_key)],
)
def cancel_reservation(reservation_id: int):
    try:
        reservation = Service.cancel_reservation(reservation_id)
        return ReservationActionResponse(
            reservation_id=reservation["id"],
            status=reservation["status"],
            message="Reservation cancelled",
        )
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    orders, total = Service.list_orders(offset, limit)
    return OrderListResponse(
        orders=[OrderResponse(**_parse_order(o)) for o in orders],
        total=total,
        offset=offset,
        limit=limit,
    )


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: int):
    try:
        order = Service.get_order(order_id)
        return OrderResponse(**_parse_order(order))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


def _to_reservation_response(reservation: dict) -> ReservationResponse:
    return ReservationResponse(
        id=reservation["id"],
        sku_id=reservation["sku_id"],
        quantity=reservation["quantity"],
        status=reservation["status"],
        idempotency_key=reservation["idempotency_key"],
        created_at=datetime.fromisoformat(reservation["created_at"]),
        expires_at=datetime.fromisoformat(reservation["expires_at"]),
        confirmed_at=(
            datetime.fromisoformat(reservation["confirmed_at"])
            if reservation["confirmed_at"]
            else None
        ),
    )


def _parse_order(order: dict) -> dict:
    return {
        "id": order["id"],
        "reservation_id": order["reservation_id"],
        "sku_id": order["sku_id"],
        "quantity": order["quantity"],
        "status": order["status"],
        "created_at": datetime.fromisoformat(order["created_at"]),
        "confirmed_at": (
            datetime.fromisoformat(order["confirmed_at"])
            if order["confirmed_at"]
            else None
        ),
    }
