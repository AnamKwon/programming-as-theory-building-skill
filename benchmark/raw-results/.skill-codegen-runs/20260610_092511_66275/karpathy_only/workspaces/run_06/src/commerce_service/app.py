import os
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .models import (
    Base,
    HealthResponse,
    OrderResponse,
    ReservationCreateRequest,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustRequest,
    get_engine,
    get_session_maker,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    InvalidStateTransitionError,
    OrderNotFoundError,
    ReservationExpiredError,
    ReservationNotFoundError,
)

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
API_KEY = os.getenv("API_KEY", "test-key")

# Initialize database
engine = get_engine(DATABASE_URL)
SessionLocal = get_session_maker(engine)
Base.metadata.create_all(bind=engine)

# FastAPI app
app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    repo = Repository(db)
    return CommerceService(repo)


def validate_api_key(x_api_key: str = Depends(verify_api_key)) -> str:
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return x_api_key


# Exception handlers
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.exception_handler(InsufficientStockError)
async def insufficient_stock_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)},
    )


@app.exception_handler(ReservationExpiredError)
async def reservation_expired_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_410_GONE,
        content={"detail": str(exc)},
    )


@app.exception_handler(ReservationNotFoundError)
async def reservation_not_found_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


@app.exception_handler(OrderNotFoundError)
async def order_not_found_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


@app.exception_handler(InvalidStateTransitionError)
async def invalid_state_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)},
    )


# Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok", timestamp=datetime.utcnow())


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: SKUCreate,
    service: CommerceService = Depends(get_service),
    _: str = Depends(validate_api_key),
):
    sku = service.create_sku(
        sku_code=request.sku_code,
        name=request.name,
        description=request.description,
        stock_level=request.stock_level,
    )
    return sku


@app.post("/stock/adjust", response_model=SKUResponse)
async def adjust_stock(
    request: StockAdjustRequest,
    service: CommerceService = Depends(get_service),
    _: str = Depends(validate_api_key),
):
    sku = service.adjust_stock(request.sku_id, request.quantity_change)
    return sku


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: ReservationCreateRequest,
    service: CommerceService = Depends(get_service),
    _: str = Depends(validate_api_key),
):
    reservation = service.create_reservation(
        order_id=request.order_id,
        sku_id=request.sku_id,
        quantity=request.quantity,
        idempotency_key=request.idempotency_key,
    )
    return reservation


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    service: CommerceService = Depends(get_service),
    _: str = Depends(validate_api_key),
):
    reservation = service.confirm_reservation(reservation_id)
    return reservation


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    service: CommerceService = Depends(get_service),
    _: str = Depends(validate_api_key),
):
    reservation = service.cancel_reservation(reservation_id)
    return reservation


@app.get("/orders", response_model=dict)
async def list_orders(limit: int = 20, offset: int = 0, service: CommerceService = Depends(get_service)):
    orders, total = service.list_orders(limit=limit, offset=offset)
    return {
        "orders": [OrderResponse.model_validate(o) for o in orders],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
