from fastapi import FastAPI, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from commerce_service.repository import Repository
from commerce_service.service import (
    OrderService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
)
from commerce_service.security import verify_api_key

app = FastAPI(title="Commerce Service", version="0.1.0")
repo = Repository()
service = OrderService(repo)


def get_db() -> Session:
    db = repo.get_session()
    try:
        yield db
    finally:
        db.close()


class HealthResponse(BaseModel):
    status: str


class SKURequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)


class SKUResponse(BaseModel):
    id: str
    code: str
    name: str
    created_at: str


class StockAdjustmentRequest(BaseModel):
    quantity: int = Field(..., description="Quantity to adjust (can be negative)")


class StockResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    reserved: int


class ReservationRequest(BaseModel):
    sku_id: str
    quantity: int = Field(..., gt=0)
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    idempotency_key: str
    expires_at: str
    confirmed: bool


class OrderResponse(BaseModel):
    id: str
    reservation_id: str
    status: str
    created_at: str
    updated_at: str


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "healthy"}


@app.post("/skus", response_model=SKUResponse, dependencies=[Depends(verify_api_key)])
async def create_sku(payload: SKURequest, db: Session = Depends(get_db)):
    try:
        sku = service.create_sku(db, payload.code, payload.name)
        return {
            "id": sku.id,
            "code": sku.code,
            "name": sku.name,
            "created_at": sku.created_at.isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/skus/{sku_id}/stock", response_model=StockResponse, dependencies=[Depends(verify_api_key)]
)
async def adjust_stock(
    sku_id: str, payload: StockAdjustmentRequest, db: Session = Depends(get_db)
):
    try:
        stock = service.adjust_stock(db, sku_id, payload.quantity)
        return {
            "id": stock.id,
            "sku_id": stock.sku_id,
            "quantity": stock.quantity,
            "reserved": stock.reserved,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/skus/{sku_id}/stock", response_model=StockResponse)
async def get_stock(sku_id: str, db: Session = Depends(get_db)):
    try:
        stock = service.get_stock(db, sku_id)
        return {
            "id": stock.id,
            "sku_id": stock.sku_id,
            "quantity": stock.quantity,
            "reserved": stock.reserved,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post(
    "/reservations", response_model=ReservationResponse, dependencies=[Depends(verify_api_key)]
)
async def create_reservation(payload: ReservationRequest, db: Session = Depends(get_db)):
    try:
        reservation = service.create_reservation(
            db, payload.sku_id, payload.quantity, payload.idempotency_key
        )
        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "idempotency_key": reservation.idempotency_key,
            "expires_at": reservation.expires_at.isoformat(),
            "confirmed": reservation.is_confirmed(),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=OrderResponse,
    dependencies=[Depends(verify_api_key)],
)
async def confirm_reservation(reservation_id: str, db: Session = Depends(get_db)):
    try:
        order = service.confirm_reservation(db, reservation_id)
        return {
            "id": order.id,
            "reservation_id": order.reservation_id,
            "status": order.status,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
        }
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/cancel",
    status_code=204,
    dependencies=[Depends(verify_api_key)],
)
async def cancel_reservation(reservation_id: str, db: Session = Depends(get_db)):
    try:
        service.cancel_reservation(db, reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, db: Session = Depends(get_db)):
    try:
        order = service.get_order(db, order_id)
        return {
            "id": order.id,
            "reservation_id": order.reservation_id,
            "status": order.status,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        orders, total = service.list_orders(db, limit, offset)
        return {
            "orders": [
                {
                    "id": order.id,
                    "reservation_id": order.reservation_id,
                    "status": order.status,
                    "created_at": order.created_at.isoformat(),
                    "updated_at": order.updated_at.isoformat(),
                }
                for order in orders
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def run():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
