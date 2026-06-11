"""FastAPI application and endpoints."""

from contextlib import contextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    AdjustStockRequest,
    CreateReservationRequest,
    CreateSKURequest,
    OrderListResponse,
    ReservationResponse,
    SKUResponse,
    get_engine,
    Base,
)
from .security import verify_api_token
from .service import CommerceService

DATABASE_URL = "sqlite:///./commerce.db"

engine = get_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201)
def create_sku(
    request: CreateSKURequest,
    token: str = Depends(verify_api_token),
    db: Session = Depends(get_db),
):
    """Create a new SKU."""
    service = CommerceService(db)
    return service.create_sku(request)


@app.post("/stock/adjust")
def adjust_stock(
    request: AdjustStockRequest,
    token: str = Depends(verify_api_token),
    db: Session = Depends(get_db),
):
    """Adjust stock for a SKU."""
    service = CommerceService(db)
    return service.adjust_stock(request.sku, request.amount)


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
def create_reservation(
    request: CreateReservationRequest,
    token: str = Depends(verify_api_token),
    db: Session = Depends(get_db),
):
    """Create a reservation."""
    service = CommerceService(db)
    return service.create_reservation(request)


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
def confirm_reservation(
    reservation_id: int,
    token: str = Depends(verify_api_token),
    db: Session = Depends(get_db),
):
    """Confirm a reservation."""
    service = CommerceService(db)
    return service.confirm_reservation(reservation_id)


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: int,
    token: str = Depends(verify_api_token),
    db: Session = Depends(get_db),
):
    """Cancel a reservation."""
    service = CommerceService(db)
    return service.cancel_reservation(reservation_id)


@app.get("/orders", response_model=OrderListResponse)
def get_orders(
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db),
):
    """Get paginated orders."""
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="page must be >= 1",
        )
    if size < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="size must be >= 1",
        )

    service = CommerceService(db)
    result = service.get_orders(page, size)
    return OrderListResponse(**result)
