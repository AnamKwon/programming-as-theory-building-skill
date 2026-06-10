from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from . import __version__
from .models import (
    AdjustStockRequest,
    CreateReservationRequest,
    CreateSKURequest,
    HealthResponse,
    OrderListResponse,
    OrderResponse,
    ReservationResponse,
    SKUResponse,
    Base,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    InvalidReservationStateError,
    OrderNotFoundError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)

# Database setup
DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version=__version__)


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
async def health_check():
    return HealthResponse(status="healthy", version=__version__)


@app.post("/skus", response_model=SKUResponse)
async def create_sku(req: CreateSKURequest, service: CommerceService = Depends(get_service)):
    result = service.create_sku(req.product_id, req.name, req.initial_stock)
    return SKUResponse(**result)


@app.post("/stock/{product_id}/adjust", response_model=SKUResponse)
async def adjust_stock(
    product_id: str, req: AdjustStockRequest, service: CommerceService = Depends(get_service)
):
    try:
        result = service.adjust_stock(product_id, req.quantity_delta)
        return SKUResponse(**result)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    req: CreateReservationRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        result = service.create_reservation(req.product_id, req.quantity, req.idempotency_key)
        return ReservationResponse(**result)
    except SKUNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        result = service.confirm_reservation(reservation_id)
        return ReservationResponse(**result)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except InvalidReservationStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        result = service.cancel_reservation(reservation_id)
        return ReservationResponse(**result)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidReservationStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    result = service.list_orders(limit=limit, offset=offset)
    return OrderListResponse(**result)


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        result = service.get_order(order_id)
        return OrderResponse(**result)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
