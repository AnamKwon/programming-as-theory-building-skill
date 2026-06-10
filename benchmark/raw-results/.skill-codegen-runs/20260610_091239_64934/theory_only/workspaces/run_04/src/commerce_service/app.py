import os

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, CreateSKURequest, AdjustStockRequest, CreateReservationRequest
from .models import (
    ConfirmReservationRequest,
    CancelReservationRequest,
    SKUResponse,
    StockResponse,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
)
from .security import verify_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidStateTransitionError,
    IdempotencyViolationError,
    ServiceError,
)

# Database setup
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)):
    return CommerceService(db)


# Error handlers
@app.exception_handler(InsufficientStockError)
async def insufficient_stock_handler(request, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(ReservationNotFoundError)
async def reservation_not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ReservationExpiredError)
async def reservation_expired_handler(request, exc):
    return JSONResponse(status_code=410, content={"detail": str(exc)})


@app.exception_handler(InvalidStateTransitionError)
async def invalid_state_handler(request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(IdempotencyViolationError)
async def idempotency_violation_handler(request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(ServiceError)
async def service_error_handler(request, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# Health check
@app.get("/health")
async def health_check():
    return {"status": "ok"}


# SKU Endpoints
@app.post("/skus", response_model=SKUResponse, dependencies=[Depends(verify_api_key)])
async def create_sku(
    request: CreateSKURequest,
    service: CommerceService = Depends(get_service),
):
    """Create a new SKU."""
    sku = service.create_sku(request.sku, request.name, request.base_price)
    return SKUResponse(
        id=sku.id,
        sku=sku.sku,
        name=sku.name,
        base_price=sku.base_price,
        created_at=sku.created_at,
    )


@app.get("/skus/{sku_id}", response_model=SKUResponse)
async def get_sku(
    sku_id: int,
    service: CommerceService = Depends(get_service),
):
    """Get SKU details."""
    sku = service.repo.get_sku(sku_id)
    if not sku:
        raise HTTPException(status_code=404, detail=f"SKU {sku_id} not found")
    return SKUResponse(
        id=sku.id,
        sku=sku.sku,
        name=sku.name,
        base_price=sku.base_price,
        created_at=sku.created_at,
    )


# Stock Endpoints
@app.post(
    "/skus/{sku_id}/stock",
    response_model=StockResponse,
    dependencies=[Depends(verify_api_key)],
)
async def adjust_stock(
    sku_id: int,
    request: AdjustStockRequest,
    service: CommerceService = Depends(get_service),
):
    """Adjust stock level for a SKU."""
    stock = service.adjust_stock(sku_id, request.quantity_delta)
    return StockResponse(sku_id=stock.sku_id, quantity=stock.quantity)


@app.get("/skus/{sku_id}/stock", response_model=StockResponse)
async def get_stock(
    sku_id: int,
    service: CommerceService = Depends(get_service),
):
    """Get current stock level for a SKU."""
    stock = service.get_stock(sku_id)
    return StockResponse(sku_id=stock.sku_id, quantity=stock.quantity)


# Reservation Endpoints
@app.post(
    "/reservations",
    response_model=ReservationResponse,
    dependencies=[Depends(verify_api_key)],
)
async def create_reservation(
    request: CreateReservationRequest,
    service: CommerceService = Depends(get_service),
):
    """Create a reservation."""
    reservation, is_idempotent = service.create_reservation(
        sku_id=request.sku_id,
        quantity=request.quantity,
        ttl_seconds=request.ttl_seconds,
        idempotency_key=request.idempotency_key,
    )
    return ReservationResponse(
        id=reservation.id,
        sku_id=reservation.sku_id,
        quantity=reservation.quantity,
        status=reservation.status,
        expires_at=reservation.expires_at,
        created_at=reservation.created_at,
    )


@app.get("/reservations/{reservation_id}", response_model=ReservationResponse)
async def get_reservation(
    reservation_id: int,
    service: CommerceService = Depends(get_service),
):
    """Get reservation details."""
    reservation = service.get_reservation(reservation_id)
    return ReservationResponse(
        id=reservation.id,
        sku_id=reservation.sku_id,
        quantity=reservation.quantity,
        status=reservation.status,
        expires_at=reservation.expires_at,
        created_at=reservation.created_at,
    )


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=ReservationResponse,
    dependencies=[Depends(verify_api_key)],
)
async def confirm_reservation(
    reservation_id: int,
    request: ConfirmReservationRequest | None = None,
    service: CommerceService = Depends(get_service),
):
    """Confirm a pending reservation."""
    reservation = service.confirm_reservation(reservation_id)
    return ReservationResponse(
        id=reservation.id,
        sku_id=reservation.sku_id,
        quantity=reservation.quantity,
        status=reservation.status,
        expires_at=reservation.expires_at,
        created_at=reservation.created_at,
    )


@app.post(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
    dependencies=[Depends(verify_api_key)],
)
async def cancel_reservation(
    reservation_id: int,
    request: CancelReservationRequest | None = None,
    service: CommerceService = Depends(get_service),
):
    """Cancel a reservation."""
    reservation = service.cancel_reservation(reservation_id)
    return ReservationResponse(
        id=reservation.id,
        sku_id=reservation.sku_id,
        quantity=reservation.quantity,
        status=reservation.status,
        expires_at=reservation.expires_at,
        created_at=reservation.created_at,
    )


# Order Endpoints
@app.get(
    "/orders",
    response_model=OrderListResponse,
    dependencies=[Depends(verify_api_key)],
)
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    service: CommerceService = Depends(get_service),
):
    """List orders with pagination."""
    orders, total = service.list_orders(page, page_size)
    return OrderListResponse(
        orders=[
            OrderResponse(
                id=o.id,
                reservation_id=o.reservation_id,
                status=o.status,
                quantity_reserved=o.quantity_reserved,
                created_at=o.created_at,
            )
            for o in orders
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    service: CommerceService = Depends(get_service),
):
    """Get order details."""
    order = service.get_order(order_id)
    return OrderResponse(
        id=order.id,
        reservation_id=order.reservation_id,
        status=order.status,
        quantity_reserved=order.quantity_reserved,
        created_at=order.created_at,
    )
