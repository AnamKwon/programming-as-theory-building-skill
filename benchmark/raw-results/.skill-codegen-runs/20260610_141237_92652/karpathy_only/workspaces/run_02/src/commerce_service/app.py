from fastapi import FastAPI, Depends, HTTPException
from .models import (
    SKURequest,
    SKUResponse,
    StockAdjustRequest,
    StockAdjustResponse,
    ReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    CancelReservationResponse,
    OrderListResponse,
    HealthResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key

app = FastAPI(title="Commerce Service")

repo = Repository()
service = CommerceService(repo)


@app.get("/health", response_model=HealthResponse)
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201)
def create_sku(request: SKURequest, _: str = Depends(verify_api_key)):
    result = service.create_sku(request.sku, request.initial_stock)
    return result


@app.post("/stock/adjust", response_model=StockAdjustResponse)
def adjust_stock(request: StockAdjustRequest, _: str = Depends(verify_api_key)):
    result = service.adjust_stock(request.sku, request.amount)
    return {"sku": result["sku"], "available_stock": result["available_stock"]}


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
def create_reservation(request: ReservationRequest, _: str = Depends(verify_api_key)):
    try:
        result = service.create_reservation(
            request.sku, request.quantity, request.idempotency_key
        )
        return result
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/confirm", response_model=ConfirmReservationResponse)
def confirm_reservation(id: int, _: str = Depends(verify_api_key)):
    try:
        result = service.confirm_reservation(id)
        return result
    except ValueError as e:
        if "not pending" in str(e).lower():
            raise HTTPException(status_code=400, detail=str(e))
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/cancel", response_model=CancelReservationResponse)
def cancel_reservation(id: int, _: str = Depends(verify_api_key)):
    try:
        result = service.cancel_reservation(id)
        return result
    except ValueError as e:
        if "not pending" in str(e).lower():
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def get_orders(page: int = 1, size: int = 10, _: str = Depends(verify_api_key)):
    result = service.get_orders(page, size)
    return result
