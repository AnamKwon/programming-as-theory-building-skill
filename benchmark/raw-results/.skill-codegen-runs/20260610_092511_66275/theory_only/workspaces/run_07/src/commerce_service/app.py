from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .models import (
    OrderResponse,
    PaginatedOrderResponse,
    ReservationRequest,
    ReservationResponse,
    SKURequest,
    SKUResponse,
    StockAdjustRequest,
    StockResponse,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

# Initialize repository and service (singleton pattern)
_repository = Repository()
_service = CommerceService(_repository)


def get_service() -> CommerceService:
    return _service


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, dependencies=[Depends(verify_api_key)])
def create_sku(req: SKURequest, service: CommerceService = Depends(get_service)):
    try:
        sku = service.create_sku(req.sku, req.name, req.price)
        return SKUResponse(
            id=sku.id,
            sku=sku.sku,
            name=sku.name,
            price=sku.price,
            created_at=sku.created_at,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=StockResponse, dependencies=[Depends(verify_api_key)])
def adjust_stock(req: StockAdjustRequest, service: CommerceService = Depends(get_service)):
    try:
        stock = service.adjust_stock(req.sku_id, req.quantity)
        return StockResponse(
            sku_id=stock.sku_id,
            available=stock.available,
            reserved=stock.reserved,
            total=stock.total,
        )
    except SKUNotFoundError:
        raise HTTPException(status_code=404, detail="SKU not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, dependencies=[Depends(verify_api_key)])
def create_reservation(req: ReservationRequest, service: CommerceService = Depends(get_service)):
    try:
        reservation = service.create_reservation(req.sku_id, req.quantity, req.idempotency_key)
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            state=reservation.state,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )
    except SKUNotFoundError:
        raise HTTPException(status_code=404, detail="SKU not found")
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/reservations/{reservation_id}/confirm", response_model=dict, dependencies=[Depends(verify_api_key)])
def confirm_reservation(
    reservation_id: int, service: CommerceService = Depends(get_service)
):
    try:
        reservation, order = service.confirm_reservation(reservation_id)
        return {
            "reservation": ReservationResponse(
                id=reservation.id,
                sku_id=reservation.sku_id,
                quantity=reservation.quantity,
                state=reservation.state,
                expires_at=reservation.expires_at,
                created_at=reservation.created_at,
            ),
            "order": OrderResponse(
                id=order.id,
                sku_id=order.sku_id,
                quantity=order.quantity,
                state=order.state,
                created_at=order.created_at,
            ),
        }
    except ReservationNotFoundError:
        raise HTTPException(status_code=404, detail="Reservation not found")
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/reservations/{reservation_id}", response_model=ReservationResponse, dependencies=[Depends(verify_api_key)])
def cancel_reservation(
    reservation_id: int, service: CommerceService = Depends(get_service)
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            state=reservation.state,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )
    except ReservationNotFoundError:
        raise HTTPException(status_code=404, detail="Reservation not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=PaginatedOrderResponse)
def get_orders(limit: int = 10, offset: int = 0, service: CommerceService = Depends(get_service)):
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be non-negative")

    orders, total = service.get_orders(limit, offset)
    return PaginatedOrderResponse(
        orders=[
            OrderResponse(
                id=order.id,
                sku_id=order.sku_id,
                quantity=order.quantity,
                state=order.state,
                created_at=order.created_at,
            )
            for order in orders
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
