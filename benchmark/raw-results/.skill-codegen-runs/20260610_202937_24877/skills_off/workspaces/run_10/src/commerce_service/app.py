"""FastAPI application."""

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session

from .models import (
    OrderListResponse,
    OrderResponse,
    ReservationRequest,
    ReservationResponse,
    SKURequest,
    StockAdjustRequest,
    StockResponse,
    get_session_maker,
    init_db,
)
from .security import verify_api_token
from .service import CommerceService

app = FastAPI(title="Commerce Service", version="0.1.0")

# Initialize database
engine = init_db("sqlite:///./commerce.db")
SessionLocal = get_session_maker(engine)


def get_session() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(session: Session = Depends(get_session)) -> CommerceService:
    """Get service instance."""
    return CommerceService(session)


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: SKURequest,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
) -> dict:
    """Create a new SKU."""
    try:
        sku_model = service.create_sku(request.sku, request.initial_stock)
        return {"id": sku_model.id, "sku": sku_model.sku, "available_stock": sku_model.available_stock}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust")
async def adjust_stock(
    request: StockAdjustRequest,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
) -> StockResponse:
    """Adjust stock level."""
    try:
        sku_model = service.adjust_stock(request.sku, request.amount)
        return StockResponse(sku=sku_model.sku, available_stock=sku_model.available_stock)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: ReservationRequest,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
) -> ReservationResponse:
    """Create a reservation."""
    try:
        reservation = service.create_reservation(request.sku, request.quantity, request.idempotency_key)
        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            idempotency_key=reservation.idempotency_key,
            created_at=reservation.created_at,
        )
    except ValueError as e:
        error_msg = str(e)
        if error_msg == "Insufficient stock":
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=error_msg)


@app.post("/reservations/{id}/confirm")
async def confirm_reservation(
    id: int,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
) -> OrderResponse:
    """Confirm a reservation and create an order."""
    try:
        order = service.confirm_reservation(id)
        return OrderResponse(
            id=order.id,
            reservation_id=order.reservation_id,
            sku=order.sku,
            quantity=order.quantity,
            created_at=order.created_at,
        )
    except ValueError as e:
        error_msg = str(e)
        if error_msg == "Reservation expired":
            raise HTTPException(status_code=400, detail="Reservation expired")
        raise HTTPException(status_code=400, detail=error_msg)


@app.post("/reservations/{id}/cancel")
async def cancel_reservation(
    id: int,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
) -> ReservationResponse:
    """Cancel a reservation."""
    try:
        reservation = service.cancel_reservation(id)
        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            idempotency_key=reservation.idempotency_key,
            created_at=reservation.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders")
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    service: CommerceService = Depends(get_service),
) -> OrderListResponse:
    """Get paginated orders."""
    orders, total = service.get_orders(page, size)
    return OrderListResponse(
        items=[
            OrderResponse(
                id=order.id,
                reservation_id=order.reservation_id,
                sku=order.sku,
                quantity=order.quantity,
                created_at=order.created_at,
            )
            for order in orders
        ],
        page=page,
        size=size,
        total=total,
    )
