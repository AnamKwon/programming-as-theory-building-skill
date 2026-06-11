from fastapi import FastAPI, HTTPException, status, Depends, Query
from datetime import datetime
from commerce_service.models import (
    SKURequest,
    SKUResponse,
    StockAdjustRequest,
    StockAdjustResponse,
    ReservationRequest,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
)
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.security import validate_api_key

app = FastAPI()
repo = Repository()
service = CommerceService(repo)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201, response_model=SKUResponse)
async def create_sku(
    request: SKURequest,
    api_key: str = Depends(validate_api_key),
):
    try:
        result = service.create_sku(request.sku, request.initial_stock)
        return SKUResponse(
            id=result["id"],
            sku=result["sku"],
            available_stock=result["available_stock"],
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=StockAdjustResponse)
async def adjust_stock(
    request: StockAdjustRequest,
    api_key: str = Depends(validate_api_key),
):
    try:
        result = service.adjust_stock(request.sku, request.amount)
        return StockAdjustResponse(
            sku=result["sku"],
            available_stock=result["available_stock"],
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(
    request: ReservationRequest,
    api_key: str = Depends(validate_api_key),
):
    try:
        result = service.create_reservation(
            request.sku,
            request.quantity,
            request.idempotency_key,
        )
        return ReservationResponse(
            id=result["id"],
            sku=result["sku"],
            quantity=result["quantity"],
            status=result["status"],
            created_at=datetime.fromisoformat(result["created_at"]),
            idempotency_key=result["idempotency_key"],
        )
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/confirm")
async def confirm_reservation(
    id: int,
    api_key: str = Depends(validate_api_key),
):
    try:
        result = service.confirm_reservation(id)
        order = result["order"]
        return {
            "reservation_id": result["reservation_id"],
            "order_id": order["id"],
            "created_at": datetime.fromisoformat(order["created_at"]),
        }
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "not in PENDING" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/cancel")
async def cancel_reservation(
    id: int,
    api_key: str = Depends(validate_api_key),
):
    try:
        result = service.cancel_reservation(id)
        return {
            "reservation_id": result["reservation_id"],
            "status": result["status"],
        }
    except ValueError as e:
        if "not in PENDING" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    api_key: str = Depends(validate_api_key),
):
    try:
        result = service.list_orders(page, size)
        orders = [
            OrderResponse(
                id=order["id"],
                reservation_id=order["reservation_id"],
                created_at=datetime.fromisoformat(order["created_at"]),
            )
            for order in result["orders"]
        ]
        return OrderListResponse(
            orders=orders,
            page=result["page"],
            size=result["size"],
            total=result["total"],
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
