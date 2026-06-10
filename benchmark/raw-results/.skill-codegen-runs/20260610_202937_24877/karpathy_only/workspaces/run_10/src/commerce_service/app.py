from fastapi import FastAPI, Depends, HTTPException
from commerce_service.models import (
    CreateSKURequest, SKUResponse,
    AdjustStockRequest, AdjustStockResponse,
    CreateReservationRequest, ReservationResponse,
    ConfirmReservationResponse, CancelReservationResponse,
    OrderListResponse, HealthResponse
)
from commerce_service.security import verify_api_token
from commerce_service.service import CommerceService
from commerce_service.repository import init_db

app = FastAPI(title="Commerce Service")
service = CommerceService()


@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201)
def create_sku(request: CreateSKURequest, token: str = Depends(verify_api_token)):
    sku_data = service.create_sku(request.sku, request.initial_stock)
    return SKUResponse(
        id=sku_data["id"],
        sku=sku_data["sku"],
        available_stock=sku_data["available_stock"]
    )


@app.post("/stock/adjust", response_model=AdjustStockResponse)
def adjust_stock(request: AdjustStockRequest, token: str = Depends(verify_api_token)):
    result = service.adjust_stock(request.sku, request.amount)
    return AdjustStockResponse(sku=result["sku"], updated_stock=result["updated_stock"])


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
def create_reservation(request: CreateReservationRequest, token: str = Depends(verify_api_token)):
    reservation = service.create_reservation(request.sku, request.quantity, request.idempotency_key)
    return ReservationResponse(
        id=reservation["id"],
        sku=reservation["sku"],
        quantity=reservation["quantity"],
        status=reservation["status"],
        created_at=reservation["created_at"],
        idempotency_key=reservation["idempotency_key"]
    )


@app.post("/reservations/{id}/confirm", response_model=ConfirmReservationResponse)
def confirm_reservation(id: int, token: str = Depends(verify_api_token)):
    result = service.confirm_reservation(id)
    return ConfirmReservationResponse(
        id=result["id"],
        status=result["status"],
        order_id=result["order_id"]
    )


@app.post("/reservations/{id}/cancel", response_model=CancelReservationResponse)
def cancel_reservation(id: int, token: str = Depends(verify_api_token)):
    result = service.cancel_reservation(id)
    return CancelReservationResponse(
        id=result["id"],
        status=result["status"],
        restored_stock=result["restored_stock"]
    )


@app.get("/orders", response_model=OrderListResponse)
def get_orders(page: int = 1, size: int = 10):
    result = service.get_orders(page, size)
    return OrderListResponse(
        page=result["page"],
        size=result["size"],
        total=result["total"],
        orders=result["orders"]
    )
