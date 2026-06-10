import os
from contextlib import contextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from . import __version__
from .models import Base, OrderListResponse, OrderResponse, ReservationResponse
from .models import CreateReservationRequest, CreateSkuRequest, AdjustStockRequest
from .models import ConfirmReservationRequest, CancelReservationRequest, SkuResponse, HealthResponse
from .models import ReservationStatus
from .repository import Repository
from .security import validate_api_key
from .service import (
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    ServiceValidationError,
)

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version=__version__)


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="healthy", version=__version__)


# SKU Endpoints
@app.post("/skus", response_model=SkuResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    req: CreateSkuRequest,
    _: str = Depends(validate_api_key),
    db: Session = Depends(get_db),
):
    try:
        service = Service(Repository(db))
        sku = service.create_sku(req.sku, req.stock)
        return SkuResponse(
            id=sku.id,
            sku=sku.sku,
            stock=sku.stock,
            reserved=sku.reserved,
            available=sku.available,
            created_at=sku.created_at,
        )
    except ServiceValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/skus/{sku_id}", response_model=SkuResponse)
async def get_sku(sku_id: int, db: Session = Depends(get_db)):
    repo = Repository(db)
    sku = repo.get_sku_by_id(sku_id)
    if not sku:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SKU {sku_id} not found")
    return SkuResponse(
        id=sku.id,
        sku=sku.sku,
        stock=sku.stock,
        reserved=sku.reserved,
        available=sku.available,
        created_at=sku.created_at,
    )


@app.patch("/skus/{sku_id}/stock", response_model=SkuResponse)
async def adjust_stock(
    sku_id: int,
    req: AdjustStockRequest,
    _: str = Depends(validate_api_key),
    db: Session = Depends(get_db),
):
    try:
        service = Service(Repository(db))
        sku = service.adjust_stock(sku_id, req.delta)
        return SkuResponse(
            id=sku.id,
            sku=sku.sku,
            stock=sku.stock,
            reserved=sku.reserved,
            available=sku.available,
            created_at=sku.created_at,
        )
    except ServiceValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Reservation Endpoints
@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    req: CreateReservationRequest,
    _: str = Depends(validate_api_key),
    db: Session = Depends(get_db),
):
    try:
        service = Service(Repository(db))
        reservation = service.create_reservation(req.sku_id, req.quantity, req.idempotency_key)
        return ReservationResponse(
            id=reservation.id,
            order_id=reservation.order_id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=ReservationStatus(reservation.status),
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ServiceValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/reservations/{reservation_id}", response_model=ReservationResponse)
async def get_reservation(reservation_id: int, db: Session = Depends(get_db)):
    repo = Repository(db)
    reservation = repo.get_reservation_by_id(reservation_id)
    if not reservation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Reservation {reservation_id} not found"
        )
    return ReservationResponse(
        id=reservation.id,
        order_id=reservation.order_id,
        sku_id=reservation.sku_id,
        quantity=reservation.quantity,
        status=ReservationStatus(reservation.status),
        expires_at=reservation.expires_at,
        created_at=reservation.created_at,
    )


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    _req: ConfirmReservationRequest,
    _: str = Depends(validate_api_key),
    db: Session = Depends(get_db),
):
    try:
        service = Service(Repository(db))
        reservation = service.confirm_reservation(reservation_id)
        return ReservationResponse(
            id=reservation.id,
            order_id=reservation.order_id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=ReservationStatus(reservation.status),
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ServiceValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    _req: CancelReservationRequest,
    _: str = Depends(validate_api_key),
    db: Session = Depends(get_db),
):
    try:
        service = Service(Repository(db))
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(
            id=reservation.id,
            order_id=reservation.order_id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=ReservationStatus(reservation.status),
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ServiceValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Order Endpoints
@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, db: Session = Depends(get_db)):
    repo = Repository(db)
    reservation = repo.get_reservation_by_order_id(order_id)
    if not reservation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {order_id} not found")
    return OrderResponse(
        id=reservation.id,
        order_id=reservation.order_id,
        sku_id=reservation.sku_id,
        quantity=reservation.quantity,
        status=ReservationStatus(reservation.status),
        created_at=reservation.created_at,
        confirmed_at=reservation.confirmed_at,
    )


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(page: int = 1, page_size: int = 10, db: Session = Depends(get_db)):
    try:
        service = Service(Repository(db))
        orders, total = service.list_orders(page, page_size)
        total_pages = (total + page_size - 1) // page_size
        items = [
            OrderResponse(
                id=r.id,
                order_id=r.order_id,
                sku_id=r.sku_id,
                quantity=r.quantity,
                status=ReservationStatus(r.status),
                created_at=r.created_at,
                confirmed_at=r.confirmed_at,
            )
            for r in orders
        ]
        return OrderListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    except ServiceValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
