from fastapi import FastAPI, HTTPException, Depends, status, Query
import os

from .models import (
    SKUCreate,
    StockAdjustRequest,
    ReservationCreate,
)
from .repository import Repository
from .service import (
    Service,
    SKUNotFoundError,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationStatusError,
    ReservationExpiredError,
)
from .security import verify_api_key

app = FastAPI(title="Commerce Inventory & Order API")

# Initialize repository and service
db_path = os.getenv("DB_PATH", "commerce.db")
repo = Repository(db_path)
service = Service(repo)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    body: SKUCreate, api_key: str = Depends(verify_api_key)
):
    try:
        sku_id = service.create_sku(body.sku, body.initial_stock)
        sku_row = repo.get_sku_by_id(sku_id)
        return {
            "id": sku_row["id"],
            "sku": sku_row["sku"],
            "available_stock": sku_row["available_stock"],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", status_code=200)
async def adjust_stock(
    body: StockAdjustRequest, api_key: str = Depends(verify_api_key)
):
    try:
        result = service.adjust_stock(body.sku, body.amount)
        return result
    except SKUNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201)
async def create_reservation(
    body: ReservationCreate, api_key: str = Depends(verify_api_key)
):
    try:
        result = service.create_reservation(
            body.sku, body.quantity, body.idempotency_key
        )
        return result
    except InsufficientStockError:
        raise HTTPException(status_code=400, detail="Insufficient stock")
    except SKUNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/confirm", status_code=200)
async def confirm_reservation(
    id: int, api_key: str = Depends(verify_api_key)
):
    try:
        service.confirm_reservation(id)
        return {"status": "confirmed"}
    except ReservationExpiredError:
        raise HTTPException(status_code=400, detail="Reservation expired")
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ReservationStatusError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/cancel", status_code=200)
async def cancel_reservation(
    id: int, api_key: str = Depends(verify_api_key)
):
    try:
        service.cancel_reservation(id)
        return {"status": "cancelled"}
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ReservationStatusError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", status_code=200)
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
):
    try:
        result = service.get_orders(page, size)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
