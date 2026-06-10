"""FastAPI application and routes."""

from fastapi import FastAPI, Depends, HTTPException, Query, status
from .models import (
    HealthResponse,
    CreateSKURequest,
    SKUResponse,
    AdjustStockRequest,
    AdjustStockResponse,
    CreateReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    CancelReservationResponse,
    OrderListResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key

app = FastAPI(title="Commerce Service API")

# Dependency for repository and service
def get_repository() -> Repository:
    return Repository()


def get_service(repo: Repository = Depends(get_repository)) -> CommerceService:
    return CommerceService(repo)


@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201, response_model=SKUResponse)
def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service)
):
    result = service.create_sku(request.sku, request.initial_stock)
    return result


@app.post("/stock/adjust", response_model=AdjustStockResponse)
def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service)
):
    result = service.adjust_stock(request.sku, request.amount)
    return result


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service)
):
    result, status_code = service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )
    if status_code == 400:
        raise HTTPException(status_code=400, detail=result["detail"])
    return result


@app.post("/reservations/{id}/confirm", response_model=ConfirmReservationResponse)
def confirm_reservation(
    id: int,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service)
):
    result, status_code = service.confirm_reservation(id)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=result["detail"])
    return result


@app.post("/reservations/{id}/cancel", response_model=CancelReservationResponse)
def cancel_reservation(
    id: int,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service)
):
    result, status_code = service.cancel_reservation(id)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=result["detail"])
    return result


@app.get("/orders", response_model=OrderListResponse)
def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service)
):
    result = service.get_orders(page, size)
    return result
