from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse

from .models import (
    OrderListResponse,
    OrderResponse,
    ReservationRequest,
    ReservationResponse,
    SKURequest,
    SKUResponse,
    StockAdjustRequest,
)
from .repository import Repository
from .security import verify_api_key
from .service import CommerceService

app = FastAPI(title="Commerce Service", version="0.1.0")

repository = Repository()
service = CommerceService(repository)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
def create_sku(request: SKURequest, _: str = Depends(verify_api_key)):
    try:
        sku = service.create_sku(request.id, request.name, request.description)
        return SKUResponse.model_validate(sku)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/skus/{sku_id}", response_model=SKUResponse)
def get_sku(sku_id: str):
    try:
        sku = service.get_sku(sku_id)
        return SKUResponse.model_validate(sku)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/stock/adjust", status_code=status.HTTP_204_NO_CONTENT)
def adjust_stock(request: StockAdjustRequest, _: str = Depends(verify_api_key)):
    try:
        service.adjust_stock(request.sku_id, request.quantity_delta)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(request: ReservationRequest, _: str = Depends(verify_api_key)):
    try:
        reservation = service.create_reservation(
            request.sku_id, request.quantity, request.idempotency_key
        )
        return ReservationResponse.model_validate(reservation)
    except ValueError as e:
        if "insufficient stock" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/reservations/{reservation_id}", response_model=ReservationResponse)
def get_reservation(reservation_id: str):
    try:
        reservation = service.get_reservation(reservation_id)
        return ReservationResponse.model_validate(reservation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.patch("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
def confirm_reservation(
    reservation_id: str,
    idempotency_key: str | None = Query(None),
    _: str = Depends(verify_api_key),
):
    try:
        order = service.confirm_reservation(reservation_id, idempotency_key)
        return OrderResponse.model_validate(order)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        if "expired" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.delete("/reservations/{reservation_id}", response_model=ReservationResponse)
def cancel_reservation(reservation_id: str, _: str = Depends(verify_api_key)):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse.model_validate(reservation)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str):
    try:
        order = service.get_order(order_id)
        return OrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def list_orders(skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100)):
    try:
        orders, total = service.list_orders(skip, limit)
        return OrderListResponse(
            items=[OrderResponse.model_validate(o) for o in orders],
            total=total,
            skip=skip,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
