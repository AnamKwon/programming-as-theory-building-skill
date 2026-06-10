import os

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, AdjustStockRequest, AdjustStockResponse, ConfirmReservationResponse, CreateReservationRequest, CreateReservationResponse, CreateSKURequest, CreateSKUResponse, HealthResponse, OrderListResponse
from .repository import Repository
from .security import APIKeyValidator
from .service import (
    DuplicateReservationError,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    SKUNotFoundError,
)

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
API_KEY = os.getenv("API_KEY", "dev-key-12345")

# Database setup
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

# FastAPI app
app = FastAPI(title="Commerce Service", version="0.1.0")

# Dependencies
api_key_validator = APIKeyValidator(API_KEY)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> Service:
    return Service(Repository(db))


# === Routes ===


@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok"}


@app.post("/skus", response_model=CreateSKUResponse)
def create_sku(
    req: CreateSKURequest,
    _: str = Depends(api_key_validator),
    svc: Service = Depends(get_service),
):
    try:
        return svc.create_sku(req.sku_id, req.initial_stock)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/skus/{sku_id}/stock", response_model=AdjustStockResponse)
def adjust_stock(
    sku_id: str,
    req: AdjustStockRequest,
    _: str = Depends(api_key_validator),
    svc: Service = Depends(get_service),
):
    try:
        return svc.adjust_stock(sku_id, req.delta)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=CreateReservationResponse)
def create_reservation(
    req: CreateReservationRequest,
    _: str = Depends(api_key_validator),
    svc: Service = Depends(get_service),
):
    try:
        return svc.create_reservation(
            req.sku_id, req.quantity, req.idempotency_key, req.ttl_seconds
        )
    except SKUNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except DuplicateReservationError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ConfirmReservationResponse)
def confirm_reservation(
    reservation_id: str,
    _: str = Depends(api_key_validator),
    svc: Service = Depends(get_service),
):
    try:
        return svc.confirm_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/reservations/{reservation_id}")
def cancel_reservation(
    reservation_id: str,
    _: str = Depends(api_key_validator),
    svc: Service = Depends(get_service),
):
    try:
        svc.cancel_reservation(reservation_id)
        return {"status": "cancelled"}
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    svc: Service = Depends(get_service),
):
    return svc.list_orders(limit, offset)
