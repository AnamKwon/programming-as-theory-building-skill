from fastapi import FastAPI, Depends, status

from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
    HealthResponse,
)
from .repository import Repository, init_db, get_session
from .service import CommerceService
from .security import verify_api_token


app = FastAPI(title="Commerce Inventory & Order API")


@app.on_event("startup")
def startup_event():
    """Initialize database on startup."""
    init_db()


def get_service(session=Depends(get_session)) -> CommerceService:
    """Create a service instance with a database session."""
    repository = Repository(session)
    return CommerceService(repository)


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", status_code=status.HTTP_201_CREATED)
def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
):
    """Create a new SKU with initial stock."""
    sku = service.create_sku(request.sku, request.initial_stock)
    return {"id": sku.id, "sku": sku.sku, "available_stock": sku.available_stock}


@app.post("/stock/adjust")
def adjust_stock(
    request: AdjustStockRequest,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
):
    """Adjust stock level for a SKU."""
    sku = service.adjust_stock(request.sku, request.amount)
    return {"id": sku.id, "sku": sku.sku, "available_stock": sku.available_stock}


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
):
    """Create a reservation for a SKU."""
    reservation = service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )
    return ReservationResponse.model_validate(reservation)


@app.post("/reservations/{id}/confirm", response_model=ReservationResponse)
def confirm_reservation(
    id: int,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
):
    """Confirm a pending reservation and create an order."""
    reservation, order = service.confirm_reservation(id)
    return ReservationResponse.model_validate(reservation)


@app.post("/reservations/{id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    id: int,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
):
    """Cancel a pending reservation and restore stock."""
    reservation = service.cancel_reservation(id)
    return ReservationResponse.model_validate(reservation)


@app.get("/orders", response_model=OrderListResponse)
def get_orders(
    page: int = 1,
    size: int = 10,
    service: CommerceService = Depends(get_service),
):
    """Get paginated list of orders."""
    orders, total = service.get_orders(page, size)
    return OrderListResponse(
        items=[OrderResponse.model_validate(order) for order in orders],
        page=page,
        size=size,
        total=total,
    )
