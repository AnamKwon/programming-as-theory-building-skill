from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session, sessionmaker

from .models import CreateReservationRequest, CreateSKURequest, OrdersListResponse, AdjustStockRequest, OrderResponse, ReservationResponse, SKUResponse, get_engine
from .repository import Repository
from .security import verify_api_key
from .service import CommerceService, ConflictError, InsufficientStockError, InvalidStateError, NotFoundError

app = FastAPI(title="Commerce Service", version="0.1.0")

# Database setup
engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    repo = Repository(db)
    return CommerceService(repo)


# Health check


@app.get("/health")
def health_check() -> dict:
    return {"status": "healthy"}


# SKU endpoints


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
def create_sku(
    request: CreateSKURequest,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
) -> SKUResponse:
    try:
        result = service.create_sku(request.sku_code, request.description)
        return SKUResponse(**result)
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/skus/{sku_code}/adjust-stock", status_code=status.HTTP_200_OK)
def adjust_stock(
    sku_code: str,
    request: AdjustStockRequest,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
) -> dict:
    try:
        result = service.adjust_stock(sku_code, request.quantity_delta)
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# Reservation endpoints


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(
    request: CreateReservationRequest,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
) -> ReservationResponse:
    try:
        result = service.create_reservation(request.sku_code, request.quantity, request.idempotency_key)
        return ReservationResponse(**result)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
def confirm_reservation(
    reservation_id: str,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
) -> ReservationResponse:
    try:
        result = service.confirm_reservation(reservation_id)
        return ReservationResponse(**result)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: str,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
) -> ReservationResponse:
    try:
        result = service.cancel_reservation(reservation_id)
        return ReservationResponse(**result)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# Order endpoints


@app.get("/orders", response_model=OrdersListResponse)
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
) -> OrdersListResponse:
    result = service.get_orders(page=page, page_size=page_size)
    return OrdersListResponse(**result)


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: str,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
) -> OrderResponse:
    try:
        result = service.get_order(order_id)
        return OrderResponse(**result)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
