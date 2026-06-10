"""FastAPI application for commerce service."""

from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from commerce_service.models import (
    SKURequest,
    SKUResponse,
    AdjustStockRequest,
    ReservationRequest,
    ReservationResponse,
    OrderResponse,
    PaginatedOrdersResponse,
    ErrorResponse,
)
from commerce_service.repository import Repository, get_db
from commerce_service.security import verify_api_key
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidStateTransitionError,
    OrderNotFoundError,
)


app = FastAPI(title="Commerce Service", version="0.1.0")


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    repo = Repository(db)
    return CommerceService(repo)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    request: SKURequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    return service.create_sku(
        sku_code=request.sku_code,
        name=request.name,
        initial_stock=request.initial_stock,
    )


@app.put("/skus/{sku_id}/stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: int,
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        return service.adjust_stock(sku_id, request.quantity_delta)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: ReservationRequest,
    _: str = Depends(verify_api_key),
    idempotency_key: Optional[str] = Header(None),
    service: CommerceService = Depends(get_service),
):
    try:
        return service.reserve_stock(
            sku_id=request.sku_id,
            quantity=request.quantity,
            idempotency_key=idempotency_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        return service.confirm_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.delete("/reservations/{reservation_id}", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        return service.cancel_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/orders", response_model=PaginatedOrdersResponse)
async def list_orders(
    offset: int = 0,
    limit: int = 20,
    service: CommerceService = Depends(get_service),
):
    if offset < 0 or limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Invalid offset or limit")

    items, total = service.list_orders(offset=offset, limit=limit)
    return PaginatedOrdersResponse(items=items, total=total, offset=offset, limit=limit)


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    service: CommerceService = Depends(get_service),
):
    try:
        return service.get_order(order_id)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


