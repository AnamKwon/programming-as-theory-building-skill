import uuid
from contextlib import contextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    AdjustStockRequest,
    Base,
    ErrorResponse,
    OrderListResponse,
    OrderResponse,
    ReservationRequest,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)

# Database setup
DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


@contextmanager
def get_service():
    session = SessionLocal()
    try:
        repo = Repository(session)
        service = CommerceService(repo)
        yield service
    finally:
        session.close()


def get_db_session() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# Health Check
@app.get("/health")
async def health_check():
    return {"status": "ok"}


# SKU Endpoints
@app.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    request: SKUCreate,
    api_key: str = Depends(verify_api_key),
):
    """Create a new SKU with initial stock."""
    with get_service() as service:
        sku_id = str(uuid.uuid4())[:12]
        sku = service.create_sku(sku_id, request.name, request.quantity)
        return SKUResponse(
            id=sku.id,
            name=sku.name,
            available_stock=sku.available_stock,
            reserved_stock=sku.reserved_stock,
        )


@app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: str,
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key),
):
    """Adjust stock for a SKU."""
    with get_service() as service:
        try:
            sku = service.adjust_stock(sku_id, request.quantity)
            return SKUResponse(
                id=sku.id,
                name=sku.name,
                available_stock=sku.available_stock,
                reserved_stock=sku.reserved_stock,
            )
        except SKUNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))


# Reservation Endpoints
@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: ReservationRequest,
    api_key: str = Depends(verify_api_key),
):
    """Create a reservation for a SKU with idempotency."""
    with get_service() as service:
        try:
            reservation = service.reserve(request)
            return ReservationResponse.model_validate(reservation)
        except InsufficientStockError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except SKUNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Confirm a pending reservation."""
    with get_service() as service:
        try:
            reservation = service.confirm_reservation(reservation_id)
            return ReservationResponse.model_validate(reservation)
        except ReservationExpiredError as e:
            raise HTTPException(status_code=410, detail=str(e))
        except ReservationNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Cancel a reservation and return stock."""
    with get_service() as service:
        try:
            reservation = service.cancel_reservation(reservation_id)
            return ReservationResponse.model_validate(reservation)
        except ReservationNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))


# Order Endpoints
@app.get("/orders", response_model=OrderListResponse)
async def list_orders(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)):
    """List orders with pagination."""
    with get_service() as service:
        orders, total = service.list_orders(page, size)
        items = []
        for order in orders:
            order_items = [
                {"reservation_id": oi.reservation_id, "quantity": oi.reservation.quantity}
                for oi in order.order_items
            ]
            items.append(
                OrderResponse(
                    id=order.id,
                    state=order.state,
                    items=order_items,
                    created_at=order.created_at,
                    updated_at=order.updated_at,
                )
            )
        return OrderListResponse(items=items, total=total, page=page, size=size)


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str):
    """Get order details by ID."""
    with get_service() as service:
        try:
            order = service.get_order(order_id)
            order_items = [
                {"reservation_id": oi.reservation_id, "quantity": oi.reservation.quantity}
                for oi in order.order_items
            ]
            return OrderResponse(
                id=order.id,
                state=order.state,
                items=order_items,
                created_at=order.created_at,
                updated_at=order.updated_at,
            )
        except ReservationNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))


# Global exception handler
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return {
        "detail": "Internal server error",
        "error_code": "INTERNAL_ERROR",
    }
