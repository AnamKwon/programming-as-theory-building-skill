import os
from contextlib import contextmanager
from typing import Generator

from fastapi import FastAPI, Depends, HTTPException, status, Query
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from . import models
from .security import validate_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    ReservationAlreadyConfirmedError,
    SKUNotFoundError,
    OrderNotFoundError,
)

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_service(db: Session) -> Generator[CommerceService, None, None]:
    service = CommerceService(db)
    try:
        yield service
    finally:
        db.close()


# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# SKU endpoints
@app.post("/skus", response_model=models.SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    payload: models.SKUCreate,
    db: Session = Depends(get_db),
    _: str = Depends(validate_api_key),
):
    """Create a new SKU."""
    try:
        service = CommerceService(db)
        result = service.create_sku(payload.id, payload.name, payload.description)
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/skus/{sku_id}/stock", response_model=models.StockResponse)
async def adjust_stock(
    sku_id: str,
    payload: models.StockAdjust,
    db: Session = Depends(get_db),
    _: str = Depends(validate_api_key),
):
    """Adjust stock level for a SKU."""
    try:
        service = CommerceService(db)
        result = service.adjust_stock(sku_id, payload.quantity)
        return result
    except SKUNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SKU {sku_id} not found")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Reservation endpoints
@app.post("/reservations", response_model=models.ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    payload: models.ReservationCreate,
    db: Session = Depends(get_db),
    _: str = Depends(validate_api_key),
):
    """Create a reservation (idempotent)."""
    try:
        service = CommerceService(db)
        result = service.reserve_inventory(payload.sku_id, payload.quantity, payload.idempotency_key)
        return result
    except InsufficientStockError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Insufficient stock for SKU {payload.sku_id}",
        )
    except SKUNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SKU {payload.sku_id} not found")
    except ReservationExpiredError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Idempotent reservation has expired",
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=models.OrderResponse)
async def confirm_reservation(
    reservation_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(validate_api_key),
):
    """Confirm a reservation and create an order."""
    try:
        service = CommerceService(db)
        result = service.confirm_reservation(reservation_id)
        return result
    except ReservationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Reservation {reservation_id} not found")
    except ReservationExpiredError:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Reservation has expired")
    except ReservationAlreadyConfirmedError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reservation is not in active status")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=models.ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(validate_api_key),
):
    """Cancel a reservation and release reserved stock."""
    try:
        service = CommerceService(db)
        result = service.cancel_reservation(reservation_id)
        return result
    except ReservationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Reservation {reservation_id} not found")
    except ReservationAlreadyConfirmedError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reservation is not in active status")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Order endpoints
@app.get("/orders/{order_id}", response_model=models.OrderResponse)
async def get_order(order_id: str, db: Session = Depends(get_db)):
    """Retrieve a specific order."""
    try:
        service = CommerceService(db)
        result = service.get_order(order_id)
        return result
    except OrderNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {order_id} not found")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=models.OrderListResponse)
async def list_orders(
    cursor: str | None = Query(None, description="Pagination cursor (order ID)"),
    limit: int = Query(20, ge=1, le=100, description="Max results per page"),
    db: Session = Depends(get_db),
):
    """List orders with pagination."""
    try:
        service = CommerceService(db)
        result = service.list_orders(cursor, limit)
        return result
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
