from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session

from .models import (
    HealthResponse,
    OrderListResponse,
    ReservationCancelRequest,
    ReservationConfirmRequest,
    ReservationCreateRequest,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustmentRequest,
    get_engine,
    get_session_factory,
    init_db,
)
from .security import verify_api_key
from .service import (
    CommercService,
    DuplicateReservationError,
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUAlreadyExistsError,
    SKUNotFoundError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

# Database setup (module-level)
_session_factory = None


def _init_db_session_factory():
    """Initialize the database session factory."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        init_db(engine)
        _session_factory = get_session_factory(engine)
    return _session_factory


def get_db() -> Session:
    SessionLocal = _init_db_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
def create_sku(
    sku_data: SKUCreate,
    _: Annotated[str, Depends(verify_api_key)],
    db: Session = Depends(get_db),
):
    """Create a new SKU with initial stock."""
    service = CommercService(db)
    try:
        return service.create_sku(sku_data.sku, sku_data.name, sku_data.stock)
    except SKUAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/skus/{sku_code}", response_model=SKUResponse)
def get_sku(sku_code: str, db: Session = Depends(get_db)):
    """Get SKU details including current stock and reserved quantities."""
    service = CommercService(db)
    try:
        return service.get_sku(sku_code)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.patch(
    "/skus/{sku_code}/stock",
    response_model=SKUResponse,
)
def adjust_stock(
    sku_code: str,
    adjustment: StockAdjustmentRequest,
    _: Annotated[str, Depends(verify_api_key)],
    db: Session = Depends(get_db),
):
    """Adjust stock for a SKU by delta amount."""
    service = CommercService(db)
    try:
        return service.adjust_stock(sku_code, adjustment.quantity)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(
    req: ReservationCreateRequest,
    _: Annotated[str, Depends(verify_api_key)],
    db: Session = Depends(get_db),
):
    """Create a reservation for a SKU."""
    service = CommercService(db)
    try:
        result = service.create_reservation(req.sku, req.quantity, req.idempotency_key)
        return ReservationResponse(**result)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=ReservationResponse,
)
def confirm_reservation(
    reservation_id: int,
    _: Annotated[ReservationConfirmRequest, Depends()],
    api_key: Annotated[str, Depends(verify_api_key)],
    db: Session = Depends(get_db),
):
    """Confirm a pending reservation."""
    service = CommercService(db)
    try:
        result = service.confirm_reservation(reservation_id)
        return ReservationResponse(**result)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
)
def cancel_reservation(
    reservation_id: int,
    _: Annotated[ReservationCancelRequest, Depends()],
    api_key: Annotated[str, Depends(verify_api_key)],
    db: Session = Depends(get_db),
):
    """Cancel a reservation."""
    service = CommercService(db)
    try:
        result = service.cancel_reservation(reservation_id)
        return ReservationResponse(**result)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
):
    """List orders with pagination."""
    service = CommercService(db)
    result = service.list_orders(offset=offset, limit=limit)
    return OrderListResponse(**result)
