import os

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, ErrorResponse, InventoryResponse, OrderListResponse, OrderResponse
from .models import ReservationCreate, ReservationResponse, SKUCreate, SKUResponse, StockAdjustment
from .security import verify_api_key
from .service import CommerceService

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
Base.metadata.create_all(bind=engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED, tags=["SKUs"])
async def create_sku(
    sku: SKUCreate,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Create a new SKU."""
    try:
        service = CommerceService(db)
        result = service.create_sku(sku_code=sku.sku_code, name=sku.name)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/stock", response_model=InventoryResponse, tags=["Stock"])
async def adjust_stock(
    adjustment: StockAdjustment,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Adjust stock for a SKU."""
    try:
        service = CommerceService(db)
        result = service.adjust_stock(sku_id=adjustment.sku_id, quantity_delta=adjustment.quantity_delta)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED, tags=["Reservations"])
async def create_reservation(
    reservation: ReservationCreate,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Create a reservation."""
    try:
        service = CommerceService(db)
        result = service.create_reservation(
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            idempotency_key=reservation.idempotency_key,
            ttl_seconds=reservation.ttl_seconds,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse, tags=["Reservations"])
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Confirm a reservation, creating an order."""
    try:
        service = CommerceService(db)
        result = service.confirm_reservation(reservation_id=reservation_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.delete("/reservations/{reservation_id}", response_model=ReservationResponse, tags=["Reservations"])
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Cancel a reservation."""
    try:
        service = CommerceService(db)
        result = service.cancel_reservation(reservation_id=reservation_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/orders", response_model=OrderListResponse, tags=["Orders"])
async def list_orders(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List orders with pagination."""
    try:
        service = CommerceService(db)
        result = service.list_orders(limit=limit, offset=offset)
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/orders/{order_id}", response_model=OrderResponse, tags=["Orders"])
async def get_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    """Get a specific order."""
    try:
        service = CommerceService(db)
        result = service.get_order(order_id=order_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
