import os

from fastapi import Depends, FastAPI, HTTPException, Query, status
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
    HealthResponse,
    OrderListResponse,
    create_db_engine,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    CommerceService,
    IdempotencyConflictError,
    InsufficientStockError,
    ReservationAlreadyConfirmedError,
    ReservationExpiredError,
    ReservationNotFoundError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

# Database setup - lazy initialization
_engine = None
SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        db_url = os.environ.get("DATABASE_URL", "sqlite:///commerce.db")
        _engine = create_db_engine(db_url)
    return _engine


def get_session_factory():
    global SessionLocal
    if SessionLocal is None:
        engine = get_engine()
        SessionLocal = sessionmaker(bind=engine)
    return SessionLocal


def get_db():
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    repo = Repository(db)
    return CommerceService(repo)


# Health Check
@app.get("/health", response_model=HealthResponse)
def health_check():
    return {"status": "ok"}


# SKU Management
@app.post("/skus", response_model=CreateSKUResponse)
def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        result = service.create_sku(request.sku_id, request.initial_stock)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.put("/skus/{sku_id}/stock", response_model=AdjustStockResponse)
def adjust_stock(
    sku_id: str,
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        result = service.adjust_stock(sku_id, request.adjustment)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# Reservation Management
@app.post("/reservations", response_model=CreateReservationResponse)
def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        result = service.create_reservation(
            request.sku_id,
            request.quantity,
            request.idempotency_key,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except IdempotencyConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/confirm", response_model=ConfirmReservationResponse)
def confirm_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        result = service.confirm_reservation(reservation_id)
        return result
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationAlreadyConfirmedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=CancelReservationResponse)
def cancel_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        result = service.cancel_reservation(reservation_id)
        return result
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# Order Lookup
@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    result = service.get_orders(page, page_size)
    return result
