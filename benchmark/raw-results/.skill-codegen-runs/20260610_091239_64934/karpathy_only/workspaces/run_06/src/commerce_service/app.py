"""FastAPI application with routes."""

import base64
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    CancelReservationRequest,
    ConfirmReservationRequest,
    CreateReservationRequest,
    CreateSkuRequest,
    ErrorResponse,
    OrderResponse,
    PaginatedOrdersResponse,
    ReservationResponse,
    ReservationStatus,
    SkuResponse,
    StockAdjustmentRequest,
    init_db,
)
from .security import verify_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    InvalidReservationStatusError,
    NotFoundError,
    ReservationExpiredError,
)

# ============================================================================
# Database Setup
# ============================================================================

DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

init_db(DATABASE_URL)


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
)


# ============================================================================
# Health Check
# ============================================================================


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# ============================================================================
# SKU Endpoints
# ============================================================================


@app.post("/skus", response_model=SkuResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSkuRequest,
    api_key: Annotated[str, Depends(verify_api_key)],
    db: Session = Depends(get_db),
):
    """Create a new SKU."""
    service = CommerceService(db)
    try:
        sku = service.create_sku(request.sku_code, request.initial_stock)
        return SkuResponse(
            id=sku.id,
            sku_code=sku.sku_code,
            stock_quantity=sku.stock_quantity,
            created_at=sku.created_at,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.patch("/skus/{sku_id}/stock", response_model=SkuResponse)
async def adjust_stock(
    sku_id: int,
    request: StockAdjustmentRequest,
    api_key: Annotated[str, Depends(verify_api_key)],
    db: Session = Depends(get_db),
):
    """Adjust stock quantity for a SKU."""
    service = CommerceService(db)
    try:
        sku = service.adjust_stock(sku_id, request.quantity_delta)
        return SkuResponse(
            id=sku.id,
            sku_code=sku.sku_code,
            stock_quantity=sku.stock_quantity,
            created_at=sku.created_at,
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ============================================================================
# Reservation Endpoints
# ============================================================================


@app.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: Annotated[str, Depends(verify_api_key)],
    db: Session = Depends(get_db),
):
    """Create a reservation for a SKU."""
    service = CommerceService(db)
    try:
        reservation = service.create_reservation(
            sku_id=request.sku_id,
            quantity=request.quantity,
            idempotency_key=request.idempotency_key,
            ttl_seconds=request.ttl_seconds,
        )
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=ReservationStatus(reservation.status),
            idempotency_key=reservation.idempotency_key,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    request: ConfirmReservationRequest,
    api_key: Annotated[str, Depends(verify_api_key)],
    db: Session = Depends(get_db),
):
    """Confirm a reservation and create an order."""
    service = CommerceService(db)
    try:
        reservation, order = service.confirm_reservation(reservation_id)
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=ReservationStatus(reservation.status),
            idempotency_key=reservation.idempotency_key,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidReservationStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ReservationExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    request: CancelReservationRequest,
    api_key: Annotated[str, Depends(verify_api_key)],
    db: Session = Depends(get_db),
):
    """Cancel a reservation and restore stock."""
    service = CommerceService(db)
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=ReservationStatus(reservation.status),
            idempotency_key=reservation.idempotency_key,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidReservationStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


# ============================================================================
# Order Endpoints
# ============================================================================


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    """Get order details by ID."""
    service = CommerceService(db)
    try:
        order = service.get_order(order_id)
        return OrderResponse(
            id=order.id,
            reservation_id=order.reservation_id,
            status=order.status,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@app.get("/orders", response_model=PaginatedOrdersResponse)
async def list_orders(
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
):
    """List orders with pagination."""
    service = CommerceService(db)
    orders, total, has_more = service.list_orders(limit=limit, offset=offset)

    cursor = None
    if has_more:
        next_offset = offset + limit
        cursor = base64.b64encode(f"offset:{next_offset}".encode()).decode()

    return PaginatedOrdersResponse(
        items=[
            OrderResponse(
                id=order.id,
                reservation_id=order.reservation_id,
                status=order.status,
                created_at=order.created_at,
                updated_at=order.updated_at,
            )
            for order in orders
        ],
        cursor=cursor,
        has_more=has_more,
    )
