from fastapi import FastAPI, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from .models import (
    SKUCreate,
    SKUResponse,
    StockAdjustmentRequest,
    ReservationCreate,
    ReservationResponse,
    OrderResponse,
    PaginatedOrderResponse,
)
from .repository import Repository, get_engine, get_session_factory, init_db
from .security import api_key_header, verify_api_key
from .service import (
    CommerceService,
    ConflictError,
    NotFoundError,
    ValidationError,
    ServiceError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

engine = get_engine()
session_factory = get_session_factory(engine)


@app.on_event("startup")
def startup():
    init_db(engine)


def get_db():
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    repo = Repository(db)
    return CommerceService(repo)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
def create_sku(
    payload: SKUCreate,
    service: CommerceService = Depends(get_service),
    api_key: str = Depends(api_key_header),
):
    verify_api_key(api_key)
    try:
        sku = service.create_sku(payload.id, payload.name)
        return SKUResponse.model_validate(sku)
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/skus/{sku_id}/stock", response_model=dict, status_code=status.HTTP_200_OK)
def adjust_stock(
    sku_id: str,
    payload: StockAdjustmentRequest,
    service: CommerceService = Depends(get_service),
    api_key: str = Depends(api_key_header),
):
    verify_api_key(api_key)
    try:
        inv = service.adjust_stock(sku_id, payload.quantity)
        return {
            "sku_id": inv.sku_id,
            "quantity": inv.quantity,
            "reserved": inv.reserved,
            "available": inv.quantity - inv.reserved,
        }
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_reservation(
    payload: ReservationCreate,
    service: CommerceService = Depends(get_service),
    api_key: str = Depends(api_key_header),
):
    verify_api_key(api_key)
    try:
        reservation_id, order = service.create_reservation(
            payload.sku_id, payload.quantity, payload.idempotency_key
        )
        return {
            "reservation_id": reservation_id,
            "order_id": order.id,
            "status": order.status,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
        }
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
def confirm_reservation(
    reservation_id: str,
    service: CommerceService = Depends(get_service),
    api_key: str = Depends(api_key_header),
):
    verify_api_key(api_key)
    try:
        order = service.confirm_reservation(reservation_id)
        return OrderResponse.model_validate(order)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=OrderResponse)
def cancel_reservation(
    reservation_id: str,
    service: CommerceService = Depends(get_service),
    api_key: str = Depends(api_key_header),
):
    verify_api_key(api_key)
    try:
        order = service.cancel_reservation(reservation_id)
        return OrderResponse.model_validate(order)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/orders", response_model=PaginatedOrderResponse)
def list_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    service: CommerceService = Depends(get_service),
):
    try:
        orders, total = service.list_orders(page, size)
        items = [OrderResponse.model_validate(order) for order in orders]
        pages = (total + size - 1) // size
        return PaginatedOrderResponse(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=pages,
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
