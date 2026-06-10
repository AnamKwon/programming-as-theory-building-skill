from fastapi import FastAPI, HTTPException, Depends, status, Query

from . import models
from .repository import Repository
from .service import CommerceService
from .security import verify_api_token

app = FastAPI(title="Commerce Service", version="0.1.0")

repository = Repository()
service = CommerceService(repository)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201, response_model=dict)
async def create_sku(request: models.CreateSKURequest, token: str = Depends(verify_api_token)):
    try:
        sku_record = service.create_sku(request.sku, request.initial_stock)
        return {
            "id": sku_record.id,
            "sku": sku_record.sku,
            "available_stock": sku_record.available_stock,
            "reserved_stock": sku_record.reserved_stock,
        }
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=409, detail="SKU already exists")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/stock/adjust", status_code=200, response_model=dict)
async def adjust_stock(request: models.AdjustStockRequest, token: str = Depends(verify_api_token)):
    new_stock = service.adjust_stock(request.sku, request.amount)
    if new_stock is None:
        raise HTTPException(status_code=404, detail="SKU not found")
    return {"sku": request.sku, "available_stock": new_stock}


@app.post("/reservations", status_code=201, response_model=models.ReservationResponse)
async def create_reservation(
    request: models.CreateReservationRequest,
    token: str = Depends(verify_api_token),
):
    reservation, status_result = service.create_reservation(request.sku, request.quantity, request.idempotency_key)

    if status_result == "sku_not_found":
        raise HTTPException(status_code=404, detail="SKU not found")
    elif status_result == "insufficient_stock":
        raise HTTPException(status_code=400, detail="Insufficient stock")

    return models.ReservationResponse(
        id=reservation.id,
        sku=reservation.sku,
        quantity=reservation.quantity,
        status=reservation.status,
        created_at=reservation.created_at,
        idempotency_key=reservation.idempotency_key,
    )


@app.post("/reservations/{id}/confirm", status_code=200, response_model=dict)
async def confirm_reservation(id: int, token: str = Depends(verify_api_token)):
    order, error = service.confirm_reservation(id)

    if error == "not_found":
        raise HTTPException(status_code=404, detail="Reservation not found")
    elif error == "not_pending":
        raise HTTPException(status_code=400, detail="Reservation is not in PENDING state")
    elif error == "expired":
        raise HTTPException(status_code=400, detail="Reservation expired")

    reservation = repository.get_reservation(id)
    return {
        "id": order.id,
        "reservation_id": order.reservation_id,
        "created_at": order.created_at.isoformat(),
        "status": "CONFIRMED",
    }


@app.post("/reservations/{id}/cancel", status_code=200, response_model=dict)
async def cancel_reservation(id: int, token: str = Depends(verify_api_token)):
    success, error = service.cancel_reservation(id)

    if error == "not_found":
        raise HTTPException(status_code=404, detail="Reservation not found")
    elif error == "not_pending":
        raise HTTPException(status_code=400, detail="Reservation is not in PENDING state")

    reservation = repository.get_reservation(id)
    return {
        "id": reservation.id,
        "sku": reservation.sku,
        "quantity": reservation.quantity,
        "status": "CANCELLED",
        "created_at": reservation.created_at.isoformat(),
    }


@app.get("/orders", response_model=models.OrderListResponse)
async def list_orders(page: int = Query(1, ge=1), size: int = Query(10, ge=1)):
    orders, total = service.get_orders(page, size)

    return models.OrderListResponse(
        orders=[
            models.OrderResponse(
                id=order.id,
                reservation_id=order.reservation_id,
                created_at=order.created_at,
            )
            for order in orders
        ],
        total=total,
        page=page,
        size=size,
    )
