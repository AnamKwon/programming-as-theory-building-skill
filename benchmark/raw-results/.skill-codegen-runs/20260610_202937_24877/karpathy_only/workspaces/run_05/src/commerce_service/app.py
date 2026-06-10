"""FastAPI application and route definitions."""

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .models import (
    Base,
    SessionLocal,
    engine,
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    StockResponse,
    PaginatedOrdersResponse,
    HealthResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service")


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    """Dependency to get service with repository."""
    repository = Repository(db)
    return CommerceService(repository)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint (no authentication required)."""
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Create a new SKU with initial stock."""
    try:
        sku = service.create_sku(request.sku, request.initial_stock)
        return {"id": sku.id, "sku": sku.sku, "stock": sku.stock}
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SKU already exists",
            )
        raise


@app.post("/stock/adjust", response_model=StockResponse)
async def adjust_stock(
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Adjust stock levels for a SKU."""
    return service.adjust_stock(request.sku, request.amount)


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Create a reservation with idempotency guarantee."""
    reservation = service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )
    return reservation


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Confirm a reservation and create an order."""
    order = service.confirm_reservation(reservation_id)
    return order


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Cancel a reservation and restore stock."""
    reservation = service.cancel_reservation(reservation_id)
    return reservation


@app.get("/orders", response_model=PaginatedOrdersResponse)
async def list_orders(
    page: int = 1,
    size: int = 10,
    service: CommerceService = Depends(get_service),
):
    """List orders with pagination."""
    result = service.list_orders(page, size)
    return {
        "items": result["items"],
        "page": result["page"],
        "size": result["size"],
        "total": result["total"],
    }
