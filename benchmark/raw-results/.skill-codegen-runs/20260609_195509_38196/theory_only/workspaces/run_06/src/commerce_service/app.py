"""FastAPI application for commerce service."""

import json
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    ErrorDetail,
    OrderResponse,
    OrdersListResponse,
    ReservationCreateRequest,
    ReservationResponse,
    SKUCreateRequest,
    SKUResponse,
    StockAdjustmentRequest,
    init_db,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    IdempotencyConflictError,
    InsufficientStockError,
    OrderService,
    ReservationAlreadyConfirmedError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)

# Initialize database
engine = init_db("sqlite:///commerce.db")
SessionLocal = sessionmaker(bind=engine)

app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
)


def get_db() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> OrderService:
    """Get order service."""
    repo = Repository(db)
    return OrderService(repo)


# Health check

@app.get("/health", tags=["Health"])
async def health_check():
    """Service health status."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# SKU endpoints

@app.post(
    "/skus",
    response_model=SKUResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["SKUs"],
)
async def create_sku(
    req: SKUCreateRequest,
    api_key: str = Depends(verify_api_key),
    service: OrderService = Depends(get_service),
):
    """Create a new SKU."""
    try:
        sku = service.create_sku(req.sku_id, req.name)
        details = service.get_sku_details(req.sku_id)
        return SKUResponse(**details)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/skus/{sku_id}", response_model=SKUResponse, tags=["SKUs"])
async def get_sku(
    sku_id: str,
    service: OrderService = Depends(get_service),
):
    """Get SKU details including current stock."""
    try:
        details = service.get_sku_details(sku_id)
        return SKUResponse(**details)
    except SKUNotFoundError:
        raise HTTPException(status_code=404, detail=f"SKU {sku_id} not found")


# Stock endpoints

@app.post(
    "/stock/adjust",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Stock"],
)
async def adjust_stock(
    req: StockAdjustmentRequest,
    api_key: str = Depends(verify_api_key),
    service: OrderService = Depends(get_service),
    db: Session = Depends(get_db),
):
    """Adjust stock for a SKU."""
    try:
        service.adjust_stock(req.sku_id, req.delta, req.idempotency_key)
        db.commit()
    except SKUNotFoundError:
        db.rollback()
        raise HTTPException(status_code=404, detail=f"SKU {req.sku_id} not found")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# Reservation endpoints

@app.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Reservations"],
)
async def create_reservation(
    req: ReservationCreateRequest,
    api_key: str = Depends(verify_api_key),
    service: OrderService = Depends(get_service),
    db: Session = Depends(get_db),
):
    """Create a new reservation for inventory."""
    try:
        res_id = service.create_reservation(
            req.sku_id,
            req.quantity,
            req.idempotency_key,
            req.ttl_seconds,
        )
        db.commit()
        details = service.get_reservation_details(res_id)
        return ReservationResponse(**details)
    except SKUNotFoundError:
        db.rollback()
        raise HTTPException(status_code=404, detail=f"SKU {req.sku_id} not found")
    except InsufficientStockError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Reservations"],
)
async def confirm_reservation(
    reservation_id: str,
    api_key: str = Depends(verify_api_key),
    service: OrderService = Depends(get_service),
    db: Session = Depends(get_db),
):
    """Confirm a reservation into an order."""
    try:
        order_id = service.confirm_reservation(reservation_id)
        db.commit()
        details = service.get_order_details(order_id)
        return OrderResponse(**details)
    except ReservationNotFoundError:
        db.rollback()
        raise HTTPException(status_code=404, detail=f"Reservation {reservation_id} not found")
    except ReservationExpiredError as e:
        db.rollback()
        raise HTTPException(status_code=410, detail=str(e))
    except ReservationAlreadyConfirmedError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Reservations"],
)
async def cancel_reservation(
    reservation_id: str,
    api_key: str = Depends(verify_api_key),
    service: OrderService = Depends(get_service),
    db: Session = Depends(get_db),
):
    """Cancel a pending reservation."""
    try:
        service.cancel_reservation(reservation_id)
        db.commit()
    except ReservationNotFoundError:
        db.rollback()
        raise HTTPException(status_code=404, detail=f"Reservation {reservation_id} not found")
    except ReservationAlreadyConfirmedError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# Order endpoints

@app.get(
    "/orders",
    response_model=OrdersListResponse,
    tags=["Orders"],
)
async def list_orders(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: OrderService = Depends(get_service),
):
    """List orders with pagination."""
    try:
        orders, total = service.list_orders(limit=limit, offset=offset)
        return OrdersListResponse(
            orders=[OrderResponse(**o) for o in orders],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom exception handler for HTTP errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
        },
    )
