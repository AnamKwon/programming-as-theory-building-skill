import os
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    AdjustStockRequest,
    AdjustStockResponse,
    CancelReservationResponse,
    ConfirmReservationResponse,
    CreateReservationRequest,
    CreateReservationResponse,
    CreateSKURequest,
    CreateSKUResponse,
    ErrorResponse,
    HealthResponse,
    OrderListResponse,
    Base,
)
from .repository import Repository
from .security import validate_api_key
from .service import (
    CommerceService,
    DuplicateRequestError,
    ExpiredReservationError,
    InsufficientStockError,
    InvalidReservationStateError,
)

database_url = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(
    database_url,
    connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="1.0.0",
)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    repo = Repository(db)
    return CommerceService(repo)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(status="healthy", timestamp=datetime.utcnow())


@app.post(
    "/skus",
    response_model=CreateSKUResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(validate_api_key),
    service: CommerceService = Depends(get_service),
) -> CreateSKUResponse:
    try:
        result = service.create_sku(request.sku_id, request.initial_stock)
        return CreateSKUResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.put("/skus/{sku_id}/stock", response_model=AdjustStockResponse)
async def adjust_stock(
    sku_id: str,
    request: AdjustStockRequest,
    _: str = Depends(validate_api_key),
    service: CommerceService = Depends(get_service),
) -> AdjustStockResponse:
    try:
        result = service.adjust_stock(sku_id, request.quantity_delta)
        return AdjustStockResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post(
    "/reservations",
    response_model=CreateReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(validate_api_key),
    service: CommerceService = Depends(get_service),
) -> CreateReservationResponse:
    try:
        result, was_cached = service.create_reservation(
            request.sku_id, request.quantity, request.idempotency_key
        )
        response = CreateReservationResponse(**result)
        if was_cached:
            return response
        return response
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@app.put(
    "/reservations/{reservation_id}/confirm",
    response_model=ConfirmReservationResponse,
)
async def confirm_reservation(
    reservation_id: str,
    _: str = Depends(validate_api_key),
    service: CommerceService = Depends(get_service),
) -> ConfirmReservationResponse:
    try:
        result = service.confirm_reservation(reservation_id)
        return ConfirmReservationResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ExpiredReservationError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e),
        )
    except InvalidReservationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@app.put(
    "/reservations/{reservation_id}/cancel",
    response_model=CancelReservationResponse,
)
async def cancel_reservation(
    reservation_id: str,
    _: str = Depends(validate_api_key),
    service: CommerceService = Depends(get_service),
) -> CancelReservationResponse:
    try:
        result = service.cancel_reservation(reservation_id)
        return CancelReservationResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidReservationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    limit: int = Query(10, ge=1, le=100),
    cursor: str | None = Query(None),
    _: str = Depends(validate_api_key),
    service: CommerceService = Depends(get_service),
) -> OrderListResponse:
    result = service.get_orders(limit=limit, cursor=cursor)
    return OrderListResponse(**result)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return {
        "error": exc.detail,
        "detail": exc.detail,
    }
