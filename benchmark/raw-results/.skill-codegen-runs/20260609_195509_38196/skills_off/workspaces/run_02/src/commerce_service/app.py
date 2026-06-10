import os

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base
from .repository import Repository
from .security import auth
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)
from .models import (
    AdjustStockRequest,
    CreateReservationRequest,
    CreateSKURequest,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

db_url = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(db_url, connect_args={"check_same_thread": False} if "sqlite" in db_url else {})
Base.metadata.create_all(bind=engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    return CommerceService(Repository(db))


def verify_api_key(x_api_key: str | None = Header(None)) -> None:
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )
    auth.verify(x_api_key)


# Health check


@app.get("/health")
def health_check():
    return {"status": "ok"}


# SKU Management


@app.post("/skus")
def create_sku(
    req: CreateSKURequest,
    service: CommerceService = Depends(get_service),
    _: None = Depends(verify_api_key),
):
    try:
        return service.create_sku(req.code)
    except Exception as e:
        service.repo.rollback()
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU already exists")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/stock/adjust")
def adjust_stock(
    req: AdjustStockRequest,
    service: CommerceService = Depends(get_service),
    _: None = Depends(verify_api_key),
):
    try:
        return service.adjust_stock(req.sku_code, req.delta)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Reservations


@app.post("/reservations")
def create_reservation(
    req: CreateReservationRequest,
    service: CommerceService = Depends(get_service),
    _: None = Depends(verify_api_key),
):
    try:
        return service.create_reservation(req.sku_code, req.quantity, req.idempotency_key)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm")
def confirm_reservation(
    reservation_id: int,
    service: CommerceService = Depends(get_service),
    _: None = Depends(verify_api_key),
):
    try:
        return service.confirm_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel")
def cancel_reservation(
    reservation_id: int,
    service: CommerceService = Depends(get_service),
    _: None = Depends(verify_api_key),
):
    try:
        return service.cancel_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# Orders


@app.get("/orders")
def list_orders(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: CommerceService = Depends(get_service),
    _: None = Depends(verify_api_key),
):
    return service.list_orders(limit, offset)


@app.get("/orders/{order_id}")
def get_order(order_id: int, service: CommerceService = Depends(get_service)):
    try:
        return service.get_order(order_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
