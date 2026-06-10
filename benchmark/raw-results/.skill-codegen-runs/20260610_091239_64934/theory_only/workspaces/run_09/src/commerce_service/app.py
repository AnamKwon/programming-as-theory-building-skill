from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    CreateReservationRequest,
    CreateSKURequest,
    AdjustStockRequest,
    Base,
    ErrorResponse,
    OrderListResponse,
    OrderResponse,
    ReservationResponse,
    SKUResponse,
    StockResponse,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    CommerceService,
    IdempotencyKeyExistsError,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)

DATABASE_URL = "sqlite:///./commerce.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_repository() -> Repository:
    session = SessionLocal()
    try:
        yield Repository(session)
    finally:
        session.close()


def get_service(repo: Repository = Depends(get_repository)) -> CommerceService:
    return CommerceService(repo)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


@app.post(
    "/skus",
    response_model=SKUResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["skus"],
    dependencies=[Depends(verify_api_key)],
)
async def create_sku(
    request: CreateSKURequest,
    service: CommerceService = Depends(get_service),
):
    try:
        sku = service.create_sku(request.sku_code, request.name, request.description)
        return SKUResponse(**sku)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@app.post(
    "/stocks/adjust",
    response_model=StockResponse,
    tags=["stocks"],
    dependencies=[Depends(verify_api_key)],
)
async def adjust_stock(
    request: AdjustStockRequest,
    service: CommerceService = Depends(get_service),
):
    try:
        stock = service.adjust_stock(request.sku_code, request.quantity)
        return stock
    except SKUNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["reservations"],
    dependencies=[Depends(verify_api_key)],
)
async def create_reservation(
    request: CreateReservationRequest,
    service: CommerceService = Depends(get_service),
):
    try:
        reservation = service.create_reservation(
            request.sku_code,
            request.quantity,
            request.idempotency_key,
            request.reservation_duration_seconds,
        )
        return reservation
    except SKUNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except IdempotencyKeyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=dict,
    tags=["reservations"],
    dependencies=[Depends(verify_api_key)],
)
async def confirm_reservation(
    reservation_id: int,
    service: CommerceService = Depends(get_service),
):
    try:
        reservation, order = service.confirm_reservation(reservation_id)
        return {"reservation": reservation, "order": order}
    except ReservationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ReservationExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
    tags=["reservations"],
    dependencies=[Depends(verify_api_key)],
)
async def cancel_reservation(
    reservation_id: int,
    service: CommerceService = Depends(get_service),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return reservation
    except ReservationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get(
    "/orders",
    response_model=OrderListResponse,
    tags=["orders"],
)
async def list_orders(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    service: CommerceService = Depends(get_service),
):
    result = service.list_orders(offset, limit)
    return OrderListResponse(**result)


@app.get(
    "/orders/{order_id}",
    response_model=OrderResponse,
    tags=["orders"],
)
async def get_order(
    order_id: int,
    service: CommerceService = Depends(get_service),
):
    try:
        order = service.get_order(order_id)
        return OrderResponse(**order)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
