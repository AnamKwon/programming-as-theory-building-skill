from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from commerce_service.models import (
    AdjustStockRequest,
    HealthResponse,
    InventoryResponse,
    OrderResponse,
    ReservationRequest,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    init_db,
)
from commerce_service.repository import Repository
from commerce_service.security import verify_api_key
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

# Initialize database
engine, SessionLocal = init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    repo = Repository(db)
    return CommerceService(repo)


# Health check
@app.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(status="ok", timestamp=datetime.utcnow())


# SKU endpoints
@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
def create_sku(
    sku_data: SKUCreate,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        sku = service.create_sku(sku_data.id, sku_data.name, sku_data.price)
        return SKUResponse.model_validate(sku)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get("/skus", response_model=list[SKUResponse])
def list_skus(service: CommerceService = Depends(get_service)):
    skus = service.list_skus()
    return [SKUResponse.model_validate(sku) for sku in skus]


@app.get("/skus/{sku_id}", response_model=SKUResponse)
def get_sku(sku_id: str, service: CommerceService = Depends(get_service)):
    try:
        sku = service.get_sku(sku_id)
        return SKUResponse.model_validate(sku)
    except SKUNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU {sku_id} not found",
        )


# Stock management
@app.get("/inventory/{sku_id}", response_model=InventoryResponse)
def get_inventory(sku_id: str, service: CommerceService = Depends(get_service)):
    try:
        inventory = service.get_inventory(sku_id)
        return InventoryResponse.model_validate(inventory)
    except SKUNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory for SKU {sku_id} not found",
        )


@app.patch("/inventory/{sku_id}", response_model=InventoryResponse)
def adjust_stock(
    sku_id: str,
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        inventory = service.adjust_stock(sku_id, request.quantity_change)
        return InventoryResponse.model_validate(inventory)
    except SKUNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU {sku_id} not found",
        )


# Reservation endpoints
@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(
    request: ReservationRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        reservation = service.create_reservation(
            request.sku_id, request.quantity, request.idempotency_key
        )
        return ReservationResponse.model_validate(reservation)
    except SKUNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU {request.sku_id} not found",
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@app.get("/reservations/{reservation_id}", response_model=ReservationResponse)
def get_reservation(
    reservation_id: str, service: CommerceService = Depends(get_service)
):
    try:
        reservation = service.get_reservation(reservation_id)
        return ReservationResponse.model_validate(reservation)
    except ReservationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found",
        )
    except ReservationExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
def confirm_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        reservation = service.confirm_reservation(reservation_id)
        return ReservationResponse.model_validate(reservation)
    except ReservationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found",
        )
    except ReservationExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e),
        )
    except (ValueError, InsufficientStockError) as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@app.delete("/reservations/{reservation_id}", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse.model_validate(reservation)
    except ReservationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found",
        )
    except ReservationExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


# Order endpoints
@app.get("/orders", response_model=dict)
def list_orders(
    skip: int = 0,
    limit: int = 20,
    service: CommerceService = Depends(get_service),
):
    if skip < 0 or limit <= 0 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pagination parameters",
        )

    orders, total = service.list_orders(skip, limit)
    return {
        "items": [OrderResponse.model_validate(order) for order in orders],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str, db: Session = Depends(get_db)):
    repo = Repository(db)
    order = repo.get_order(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found",
        )
    return OrderResponse.model_validate(order)
