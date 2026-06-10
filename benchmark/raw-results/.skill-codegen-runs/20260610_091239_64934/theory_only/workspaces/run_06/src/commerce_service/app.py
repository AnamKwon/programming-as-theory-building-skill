from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    AdjustStockRequest,
    ConfirmReservationRequest,
    CreateReservationRequest,
    CreateSKURequest,
    ErrorResponse,
    OrderListResponse,
    OrderResponse,
    ReservationResponse,
    SKUResponse,
    init_db,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    ServiceError,
)

engine = init_db()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI(title="Commerce Service", version="1.0.0")


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
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, dependencies=[Depends(verify_api_key)])
async def create_sku(
    request: CreateSKURequest,
    service: Service = Depends(get_service),
):
    try:
        db_sku = service.create_sku(request.sku, request.name, request.initial_stock)
        return SKUResponse(
            sku=db_sku.sku,
            name=db_sku.name,
            available_stock=db_sku.total_stock - db_sku.reserved_stock,
            reserved_stock=db_sku.reserved_stock,
            total_stock=db_sku.total_stock,
        )
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/stock/adjust", response_model=SKUResponse, dependencies=[Depends(verify_api_key)])
async def adjust_stock(
    request: AdjustStockRequest,
    service: Service = Depends(get_service),
):
    try:
        service.adjust_stock(request.sku, request.quantity)
        db_sku = service.get_sku(request.sku)
        return SKUResponse(
            sku=db_sku.sku,
            name=db_sku.name,
            available_stock=db_sku.total_stock - db_sku.reserved_stock,
            reserved_stock=db_sku.reserved_stock,
            total_stock=db_sku.total_stock,
        )
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, dependencies=[Depends(verify_api_key)])
async def create_reservation(
    request: CreateReservationRequest,
    service: Service = Depends(get_service),
):
    try:
        reservation = service.create_reservation(request.sku, request.quantity, request.idempotency_key)
        return ReservationResponse(
            reservation_id=reservation.reservation_id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=OrderResponse,
    dependencies=[Depends(verify_api_key)],
)
async def confirm_reservation(
    reservation_id: str,
    request: ConfirmReservationRequest,
    service: Service = Depends(get_service),
):
    try:
        order = service.confirm_reservation(reservation_id, request.idempotency_key)
        return OrderResponse(
            order_id=order.order_id,
            sku=order.sku,
            quantity=order.quantity,
            created_at=order.created_at,
        )
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", dependencies=[Depends(verify_api_key)])
async def cancel_reservation(
    reservation_id: str,
    service: Service = Depends(get_service),
):
    try:
        service.cancel_reservation(reservation_id)
        return {"status": "cancelled"}
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=OrderListResponse, dependencies=[Depends(verify_api_key)])
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    service: Service = Depends(get_service),
):
    try:
        orders, total = service.list_orders(page, page_size)
        return OrderListResponse(
            orders=[
                OrderResponse(order_id=o.order_id, sku=o.sku, quantity=o.quantity, created_at=o.created_at)
                for o in orders
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders/{order_id}", response_model=OrderResponse, dependencies=[Depends(verify_api_key)])
async def get_order(
    order_id: str,
    service: Service = Depends(get_service),
):
    try:
        order = service.get_order(order_id)
        return OrderResponse(
            order_id=order.order_id,
            sku=order.sku,
            quantity=order.quantity,
            created_at=order.created_at,
        )
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
