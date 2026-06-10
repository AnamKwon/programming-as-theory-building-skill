from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .models import (
    init_db,
    get_session_factory,
    get_database_url,
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    PaginatedOrdersResponse,
    HealthResponse,
)
from .service import CommerceService
from .security import verify_api_key

DATABASE_URL = get_database_url()
SessionLocal = get_session_factory(DATABASE_URL)

app = FastAPI(title="Commerce Service API")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    return CommerceService(db)


@app.on_event("startup")
def startup():
    init_db(DATABASE_URL)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        sku = service.create_sku(request.sku, request.initial_stock)
        return {
            "sku": sku.sku,
            "initial_stock": sku.initial_stock,
            "available_stock": sku.available_stock,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust")
async def adjust_stock(
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        sku = service.adjust_stock(request.sku, request.amount)
        return {"sku": sku.sku, "available_stock": sku.available_stock}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        reservation = service.create_reservation(
            request.sku, request.quantity, request.idempotency_key
        )
        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
        )
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        order = service.confirm_reservation(reservation_id)
        return OrderResponse(
            id=order.id,
            reservation_id=order.reservation_id,
            status=order.status,
            created_at=order.created_at,
        )
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "not pending" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation is not pending")
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Reservation not found")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
        )
    except ValueError as e:
        if "not pending" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation is not pending")
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Reservation not found")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=PaginatedOrdersResponse)
async def list_orders(
    page: int = 1,
    size: int = 10,
    service: CommerceService = Depends(get_service),
):
    orders, total = service.list_orders(page, size)
    return PaginatedOrdersResponse(
        items=[
            OrderResponse(
                id=order.id,
                reservation_id=order.reservation_id,
                status=order.status,
                created_at=order.created_at,
            )
            for order in orders
        ],
        page=page,
        size=size,
        total=total,
    )
