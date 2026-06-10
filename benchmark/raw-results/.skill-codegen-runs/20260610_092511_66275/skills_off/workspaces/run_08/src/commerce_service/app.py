from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .models import (
    Base,
    get_engine,
    get_session_factory,
    CreateSKURequest,
    SKUResponse,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    ListOrdersResponse,
    OrderItemResponse,
)
from .repository import Repository
from .service import (
    Service,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidStateTransitionError,
)
from .security import verify_api_key

app = FastAPI(title="Commerce Service")

engine = get_engine()
SessionLocal = get_session_factory(engine)

Base.metadata.create_all(bind=engine)


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
async def health_check():
    return {"status": "healthy"}


@app.post("/skus", response_model=SKUResponse)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    sku = service.create_sku(request.code, request.name, request.description, request.initial_stock)
    return SKUResponse.model_validate(sku)


@app.post("/skus/{sku_id}/stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: int,
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        sku = service.adjust_stock(sku_id, request.quantity_change)
        return SKUResponse.model_validate(sku)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        reservation = service.create_reservation(
            request.sku_id,
            request.quantity,
            request.idempotency_key,
        )
        return ReservationResponse.model_validate(reservation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        reservation = service.confirm_reservation(reservation_id)
        return ReservationResponse.model_validate(reservation)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse.model_validate(reservation)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/orders", response_model=ListOrdersResponse)
async def list_orders(
    page: int = 1,
    page_size: int = 10,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    if page < 1 or page_size < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="page and page_size must be >= 1")
    if page_size > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="page_size cannot exceed 100")

    offset = (page - 1) * page_size
    orders, total = service.get_orders(limit=page_size, offset=offset)

    items = []
    for order in orders:
        reservation_ids = [int(rid) for rid in order.reservation_ids.split(",") if rid]
        order_items = []
        for rid in reservation_ids:
            db = SessionLocal()
            repo = Repository(db)
            res = repo.get_reservation(rid)
            if res:
                order_items.append(OrderItemResponse(reservation_id=rid, sku_id=res.sku_id, quantity=res.quantity))
            db.close()

        items.append(OrderResponse(id=order.id, status=order.status, created_at=order.created_at, items=order_items))

    return ListOrdersResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
