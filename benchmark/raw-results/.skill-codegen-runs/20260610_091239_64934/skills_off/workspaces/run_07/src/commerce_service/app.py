"""FastAPI application."""

import os
from contextlib import contextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    AdjustStockRequest,
    CancelReservationRequest,
    ConfirmReservationRequest,
    CreateReservationRequest,
    CreateSKURequest,
    ErrorResponse,
    OrdersListResponse,
    OrderResponse,
    ReservationResponse,
    SKUResponse,
    StockResponse,
    Base,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpirationError,
)

db_url = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(db_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
)


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/api/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    request: CreateSKURequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Create a new SKU."""
    try:
        repo = Repository(db)
        service = CommerceService(repo)
        result = service.create_sku(request.id, request.name)
        return SKUResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/stock/adjust", response_model=StockResponse)
async def adjust_stock(
    request: AdjustStockRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Adjust stock for a SKU."""
    try:
        repo = Repository(db)
        service = CommerceService(repo)
        result = service.adjust_stock(request.sku_id, request.delta)
        return StockResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Create a reservation for inventory."""
    try:
        repo = Repository(db)
        service = CommerceService(repo)
        result = service.create_reservation(
            request.sku_id,
            request.quantity,
            request.idempotency_key,
            request.ttl_seconds,
        )
        return ReservationResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/api/reservations/{reservation_id}/confirm",
    response_model=ReservationResponse,
)
async def confirm_reservation(
    reservation_id: str,
    request: ConfirmReservationRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Confirm a reservation."""
    try:
        repo = Repository(db)
        service = CommerceService(repo)
        result = service.confirm_reservation(reservation_id, request.idempotency_key)
        return ReservationResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationExpirationError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/api/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
)
async def cancel_reservation(
    reservation_id: str,
    request: CancelReservationRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Cancel a reservation."""
    try:
        repo = Repository(db)
        service = CommerceService(repo)
        result = service.cancel_reservation(reservation_id, request.idempotency_key)
        return ReservationResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/orders", response_model=OrdersListResponse)
async def list_orders(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """List orders with pagination."""
    try:
        if skip < 0 or limit < 1:
            raise HTTPException(status_code=400, detail="Invalid pagination parameters")

        repo = Repository(db)
        service = CommerceService(repo)
        result = service.get_orders(skip, limit)
        return OrdersListResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
