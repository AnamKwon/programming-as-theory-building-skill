from datetime import datetime

from fastapi import FastAPI, HTTPException, status, Depends, Query

from .models import (
    HealthResponse,
    SKUCreate,
    StockAdjust,
    ReservationRequest,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key

app = FastAPI(title="Commerce Service")

def get_service():
    if not hasattr(app.state, "service"):
        repository = Repository()
        app.state.service = CommerceService(repository)
    return app.state.service


@app.get("/health", response_model=HealthResponse)
def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
def create_sku(sku_data: SKUCreate, _: str = Depends(verify_api_key)):
    service = get_service()
    success = service.create_sku(sku_data.sku, sku_data.initial_stock)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SKU already exists",
        )
    return {"sku": sku_data.sku, "initial_stock": sku_data.initial_stock}


@app.post("/stock/adjust")
def adjust_stock(adjust_data: StockAdjust, _: str = Depends(verify_api_key)):
    service = get_service()
    updated_stock = service.adjust_stock(adjust_data.sku, adjust_data.amount)
    if updated_stock is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SKU not found",
        )
    return {"sku": adjust_data.sku, "available_stock": updated_stock}


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
def create_reservation(
    reservation_data: ReservationRequest, _: str = Depends(verify_api_key)
):
    service = get_service()
    reservation, error = service.create_reservation(
        reservation_data.sku,
        reservation_data.quantity,
        reservation_data.idempotency_key,
    )
    if error:
        if error == "Insufficient stock":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )
    return ReservationResponse(
        id=reservation["id"],
        sku=reservation["sku"],
        quantity=reservation["quantity"],
        idempotency_key=reservation["idempotency_key"],
        status=reservation["status"],
        created_at=datetime.fromisoformat(reservation["created_at"]),
    )


@app.post("/reservations/{id}/confirm", response_model=OrderResponse)
def confirm_reservation(id: int, _: str = Depends(verify_api_key)):
    service = get_service()
    order, error = service.confirm_reservation(id)
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )
    return OrderResponse(
        id=order["id"],
        reservation_id=order["reservation_id"],
        created_at=datetime.fromisoformat(order["created_at"]),
    )


@app.post("/reservations/{id}/cancel", response_model=ReservationResponse)
def cancel_reservation(id: int, _: str = Depends(verify_api_key)):
    service = get_service()
    reservation, error = service.cancel_reservation(id)
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )
    return ReservationResponse(
        id=reservation["id"],
        sku=reservation["sku"],
        quantity=reservation["quantity"],
        idempotency_key=reservation["idempotency_key"],
        status=reservation["status"],
        created_at=datetime.fromisoformat(reservation["created_at"]),
    )


@app.get("/orders", response_model=OrderListResponse)
def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    _: str = Depends(verify_api_key),
):
    service = get_service()
    orders, total = service.get_orders(page, size)
    return OrderListResponse(
        orders=[
            OrderResponse(
                id=o["id"],
                reservation_id=o["reservation_id"],
                created_at=datetime.fromisoformat(o["created_at"]),
            )
            for o in orders
        ],
        page=page,
        size=size,
        total=total,
    )
