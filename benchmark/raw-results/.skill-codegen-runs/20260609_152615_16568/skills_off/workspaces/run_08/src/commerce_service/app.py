from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse

from .models import (
    OrderListResponse,
    OrderResponse,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustRequest,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    DuplicateReservationError,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    SKUNotFoundError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

repo = Repository()
service = Service(repo)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
def create_sku(
    payload: SKUCreate,
    _: str = Depends(verify_api_key),
):
    try:
        sku = service.create_sku(payload.code, payload.name)
        return SKUResponse(id=sku.id, code=sku.code, name=sku.name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", status_code=status.HTTP_204_NO_CONTENT)
def adjust_stock(
    payload: StockAdjustRequest,
    _: str = Depends(verify_api_key),
):
    try:
        service.adjust_stock(payload.sku_id, payload.quantity_delta)
    except SKUNotFoundError:
        raise HTTPException(status_code=404, detail="SKU not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_reservation(
    payload: ReservationCreate,
    _: str = Depends(verify_api_key),
):
    try:
        reservation = service.create_reservation(
            sku_id=payload.sku_id,
            quantity=payload.quantity,
            idempotency_key=payload.idempotency_key,
            reservation_ttl_seconds=payload.reservation_ttl_seconds,
        )
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=reservation.status,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )
    except DuplicateReservationError:
        raise HTTPException(status_code=409, detail="Idempotency key already used")
    except SKUNotFoundError:
        raise HTTPException(status_code=404, detail="SKU not found")
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
)
def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
):
    try:
        order = service.confirm_reservation(reservation_id)
        return OrderResponse(
            id=order.id,
            reservation_id=order.reservation_id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            status=order.status,
            created_at=order.created_at,
            confirmed_at=order.confirmed_at,
        )
    except ReservationNotFoundError:
        raise HTTPException(status_code=404, detail="Reservation not found")
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/reservations/{reservation_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
):
    try:
        service.cancel_reservation(reservation_id)
    except ReservationNotFoundError:
        raise HTTPException(status_code=404, detail="Reservation not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    orders, total = service.get_orders(offset, limit)
    return OrderListResponse(
        items=[
            OrderResponse(
                id=order.id,
                reservation_id=order.reservation_id,
                sku_id=order.sku_id,
                quantity=order.quantity,
                status=order.status,
                created_at=order.created_at,
                confirmed_at=order.confirmed_at,
            )
            for order in orders
        ],
        total=total,
        offset=offset,
        limit=limit,
    )
