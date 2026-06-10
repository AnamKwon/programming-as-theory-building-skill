from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from .models import (
    AdjustStockRequest,
    CancelReservationRequest,
    ConfirmReservationRequest,
    ConfirmReservationResponse,
    CreateReservationRequest,
    CreateReservationResponse,
    CreateSKURequest,
    CreateSKUResponse,
    ListOrdersResponse,
    OrderResponse,
    get_engine,
    get_session_factory,
    init_db,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    InsufficientStockError,
    InvalidReservationStateError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    SKUNotFoundError,
)

engine = get_engine()
SessionLocal = get_session_factory(engine)
init_db(engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> Service:
    repo = Repository(db)
    return Service(repo)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", response_model=CreateSKUResponse)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    sku = service.create_sku(request.code, request.description)
    return CreateSKUResponse(
        id=sku.id,
        code=sku.code,
        description=sku.description,
        created_at=sku.created_at,
    )


@app.patch("/stock/{sku_id}")
async def adjust_stock(
    sku_id: str,
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        stock = service.adjust_stock(sku_id, request.adjustment)
        return {"sku_id": stock.sku_id, "quantity": stock.quantity}
    except SKUNotFoundError:
        raise HTTPException(status_code=404, detail="SKU not found")
    except InsufficientStockError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=CreateReservationResponse)
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        reservation = service.create_reservation(
            request.sku_id, request.quantity, request.idempotency_key
        )
        return CreateReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
        )
    except SKUNotFoundError:
        raise HTTPException(status_code=404, detail="SKU not found")
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ConfirmReservationResponse)
async def confirm_reservation(
    reservation_id: str,
    _: CancelReservationRequest = Depends(),
    __: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        order = service.confirm_reservation(reservation_id)
        return ConfirmReservationResponse(
            order_id=order.id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            status=order.status,
            created_at=order.created_at,
        )
    except ReservationNotFoundError:
        raise HTTPException(status_code=404, detail="Reservation not found")
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except InvalidReservationStateError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: str,
    _: CancelReservationRequest = Depends(),
    __: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
        }
    except ReservationNotFoundError:
        raise HTTPException(status_code=404, detail="Reservation not found")
    except InvalidReservationStateError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/orders", response_model=ListOrdersResponse)
async def list_orders(
    offset: int = 0,
    limit: int = 10,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    orders, total = service.list_orders(offset, limit)
    return ListOrdersResponse(
        items=[
            OrderResponse(
                id=o.id,
                sku_id=o.sku_id,
                quantity=o.quantity,
                status=o.status,
                created_at=o.created_at,
            )
            for o in orders
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@app.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    order = service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderResponse(
        id=order.id,
        sku_id=order.sku_id,
        quantity=order.quantity,
        status=order.status,
        created_at=order.created_at,
    )
