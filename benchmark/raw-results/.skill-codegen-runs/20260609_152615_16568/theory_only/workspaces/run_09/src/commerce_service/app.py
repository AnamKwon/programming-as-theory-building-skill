"""FastAPI application."""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    Base,
    OrderList,
    OrderResponse,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustment,
    StockResponse,
)
from .repository import ConflictError, NotFoundError, Repository
from .security import verify_api_key
from .service import (
    ExpiredReservationError,
    InsufficientStockError,
    InvalidStateError,
    Service,
    ServiceError,
)

DATABASE_URL = "sqlite:///./commerce.db"

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=_engine)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db():
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Annotated[Session, Depends(get_db)]) -> Service:
    return Service(Repository(db))


# === Health Check ===


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# === SKU Management ===


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    sku: SKUCreate,
    _: Annotated[str, Depends(verify_api_key)],
    service: Annotated[Service, Depends(get_service)],
):
    """Create a new SKU."""
    try:
        result = service.create_sku(sku.id, sku.name, initial_stock=100)
        return result
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/skus/{sku_id}", response_model=SKUResponse)
async def get_sku(
    sku_id: str,
    service: Annotated[Service, Depends(get_service)],
):
    """Get SKU details."""
    result = service.get_sku(sku_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found")
    return result


# === Stock Management ===


@app.get("/stock/{sku_id}", response_model=StockResponse)
async def get_stock(
    sku_id: str,
    service: Annotated[Service, Depends(get_service)],
):
    """Get stock levels for a SKU."""
    try:
        return service.get_stock(sku_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/stock/{sku_id}/adjust", response_model=StockResponse)
async def adjust_stock(
    sku_id: str,
    adjustment: StockAdjustment,
    _: Annotated[str, Depends(verify_api_key)],
    service: Annotated[Service, Depends(get_service)],
):
    """Adjust inventory for a SKU."""
    try:
        return service.adjust_stock(sku_id, adjustment.quantity_delta)
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# === Reservations ===


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    reservation: ReservationCreate,
    _: Annotated[str, Depends(verify_api_key)],
    service: Annotated[Service, Depends(get_service)],
):
    """Create a reservation for inventory."""
    try:
        result = service.create_reservation(
            reservation.sku_id,
            reservation.quantity,
            reservation.idempotency_key,
        )
        return result
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/reservations/{reservation_id}", response_model=ReservationResponse)
async def get_reservation(
    reservation_id: str,
    service: Annotated[Service, Depends(get_service)],
):
    """Get reservation details."""
    try:
        return service.get_reservation(reservation_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ExpiredReservationError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: str,
    _: Annotated[str, Depends(verify_api_key)],
    service: Annotated[Service, Depends(get_service)],
):
    """Confirm a reservation, creating an order."""
    try:
        return service.confirm_reservation(reservation_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ExpiredReservationError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    _: Annotated[str, Depends(verify_api_key)],
    service: Annotated[Service, Depends(get_service)],
):
    """Cancel a reservation, releasing reserved stock."""
    try:
        return service.cancel_reservation(reservation_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# === Orders ===


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    service: Annotated[Service, Depends(get_service)],
):
    """Get order details."""
    try:
        return service.get_order(order_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.get("/orders", response_model=OrderList)
async def list_orders(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
    service: Service = Depends(get_service),
):
    """List orders with pagination."""
    try:
        return service.list_orders(page, page_size)
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
