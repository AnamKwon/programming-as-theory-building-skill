from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base
from .repository import Repository
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
    InvalidReservationStatusError,
    IdempotencyConflictError,
)
from .security import verify_api_key
from .models import (
    SKUCreate,
    SKUResponse,
    AdjustStockRequest,
    ReservationCreateRequest,
    ReservationResponse,
    ReservationConfirmRequest,
    OrderResponse,
    HealthResponse,
    ErrorResponse,
)

# Database setup
DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
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


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    repo = Repository(db)
    return CommerceService(repo)


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow()}


@app.post("/skus", response_model=SKUResponse, dependencies=[Depends(verify_api_key)])
def create_sku(
    req: SKUCreate,
    service: CommerceService = Depends(get_service),
):
    """Create a new SKU with initial stock."""
    try:
        result = service.create_sku(req.sku_id, req.name, req.initial_stock)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse, dependencies=[Depends(verify_api_key)])
def adjust_stock(
    sku_id: str,
    req: AdjustStockRequest,
    service: CommerceService = Depends(get_service),
):
    """Adjust stock for a SKU."""
    try:
        result = service.adjust_stock(sku_id, req.adjustment)
        return result
    except SKUNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU {sku_id} not found",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations", response_model=ReservationResponse, dependencies=[Depends(verify_api_key)])
def create_reservation(
    req: ReservationCreateRequest,
    service: CommerceService = Depends(get_service),
):
    """Create a reservation for a customer."""
    try:
        result = service.create_reservation(
            sku_id=req.sku_id,
            customer_id=req.customer_id,
            quantity=req.quantity,
            idempotency_key=req.idempotency_key,
        )
        return result
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except SKUNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU {req.sku_id} not found",
        )
    except IdempotencyConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse, dependencies=[Depends(verify_api_key)])
def confirm_reservation(
    reservation_id: str,
    req: ReservationConfirmRequest,
    service: CommerceService = Depends(get_service),
):
    """Confirm a reservation and create an order."""
    try:
        result = service.confirm_reservation(reservation_id)
        return result
    except ReservationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found",
        )
    except ReservationExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except InvalidReservationStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse, dependencies=[Depends(verify_api_key)])
def cancel_reservation(
    reservation_id: str,
    service: CommerceService = Depends(get_service),
):
    """Cancel a reservation and release stock."""
    try:
        result = service.cancel_reservation(reservation_id)
        return result
    except ReservationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found",
        )
    except InvalidReservationStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: str,
    service: CommerceService = Depends(get_service),
):
    """Retrieve an order by ID."""
    try:
        result = service.get_order(order_id)
        return result
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found",
        )


@app.get("/customers/{customer_id}/orders")
def list_orders(
    customer_id: str,
    skip: int = 0,
    limit: int = 10,
    service: CommerceService = Depends(get_service),
):
    """List orders for a customer with pagination."""
    if skip < 0 or limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pagination parameters. limit must be 1-100, skip must be >= 0",
        )
    result = service.list_orders(customer_id, skip, limit)
    return result
