import os

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    AdjustStockRequest,
    Base,
    HealthResponse,
    OrderListResponse,
    OrderResponse,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
)
from .security import get_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: SKUCreate, api_key: str = Depends(get_api_key), db: Session = Depends(get_db)
):
    try:
        service = CommerceService(db)
        result = service.create_sku(request.sku_id, request.name, request.initial_stock)
        return {
            "sku_id": result["sku_id"],
            "name": result["name"],
            "available_stock": result["available_stock"],
            "reserved_stock": result["reserved_stock"],
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: str,
    request: AdjustStockRequest,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    try:
        service = CommerceService(db)
        result = service.adjust_stock(sku_id, request.quantity)
        return {
            "sku_id": result["sku_id"],
            "name": result["name"],
            "available_stock": result["available_stock"],
            "reserved_stock": result["reserved_stock"],
        }
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: ReservationCreate, api_key: str = Depends(get_api_key), db: Session = Depends(get_db)
):
    try:
        service = CommerceService(db)
        result = service.create_reservation(
            request.sku_id, request.quantity, request.idempotency_key
        )
        return {
            "reservation_id": result["reservation_id"],
            "sku_id": result["sku_id"],
            "quantity": result["quantity"],
            "status": result["status"],
            "created_at": result["created_at"],
            "expires_at": result["expires_at"],
        }
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: str, api_key: str = Depends(get_api_key), db: Session = Depends(get_db)
):
    try:
        service = CommerceService(db)
        result = service.confirm_reservation(reservation_id)
        return {
            "order_id": result["order_id"],
            "status": result["status"],
            "items": result["items"],
            "created_at": result["created_at"],
            "updated_at": result["updated_at"],
        }
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (InvalidStateTransitionError, ReservationExpiredError) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str, api_key: str = Depends(get_api_key), db: Session = Depends(get_db)
):
    try:
        service = CommerceService(db)
        result = service.cancel_reservation(reservation_id)
        return {
            "reservation_id": result["reservation_id"],
            "sku_id": result["sku_id"],
            "quantity": result["quantity"],
            "status": result["status"],
            "created_at": result["created_at"],
            "expires_at": result["expires_at"],
        }
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    try:
        service = CommerceService(db)
        result = service.list_orders(page, page_size)
        return {
            "items": result["items"],
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
            "pages": result["pages"],
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, db: Session = Depends(get_db)):
    try:
        service = CommerceService(db)
        result = service.get_order(order_id)
        return {
            "order_id": result["order_id"],
            "status": result["status"],
            "items": result["items"],
            "created_at": result["created_at"],
            "updated_at": result["updated_at"],
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
