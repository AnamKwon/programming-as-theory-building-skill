import os
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Query, status
from sqlalchemy.exc import IntegrityError

from commerce_service import __version__
from commerce_service.models import (
    SKUCreate, StockAdjustment, ReservationCreate, ReservationResponse,
    OrderResponse, OrderListResponse, HealthResponse, ErrorResponse
)
from commerce_service.repository import Repository
from commerce_service.service import CommercService
from commerce_service.security import verify_api_key


app = FastAPI(title="Commerce Service", version=__version__)

_repo_instance: Repository | None = None
_service_instance: CommercService | None = None


def get_db_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///commerce.db")


def get_repository() -> Repository:
    global _repo_instance
    if _repo_instance is None:
        _repo_instance = Repository(get_db_url())
    return _repo_instance


def get_service() -> CommercService:
    global _service_instance
    if _service_instance is None:
        _service_instance = CommercService(get_repository())
    return _service_instance


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok", "version": __version__}


@app.post("/skus", dependencies=[Depends(verify_api_key)])
async def create_sku(payload: SKUCreate, svc: CommercService = Depends(get_service)):
    try:
        result = svc.create_sku(payload.sku_id, payload.name, payload.initial_stock)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/skus/{sku_id}/adjust-stock", dependencies=[Depends(verify_api_key)])
async def adjust_stock(sku_id: str, payload: StockAdjustment, svc: CommercService = Depends(get_service)):
    try:
        result = svc.adjust_stock(sku_id, payload.quantity_delta)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, dependencies=[Depends(verify_api_key)])
async def create_reservation(payload: ReservationCreate, svc: CommercService = Depends(get_service)):
    try:
        result = svc.create_reservation(
            payload.sku_id, payload.quantity, payload.idempotency_key, payload.ttl_seconds
        )
        return result
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate idempotency key")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/reservations/{res_id}/confirm", response_model=OrderResponse, dependencies=[Depends(verify_api_key)])
async def confirm_reservation(res_id: str, svc: CommercService = Depends(get_service)):
    try:
        result = svc.confirm_reservation(res_id)
        return result
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        if "expired" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/reservations/{res_id}/cancel", response_model=ReservationResponse, dependencies=[Depends(verify_api_key)])
async def cancel_reservation(res_id: str, svc: CommercService = Depends(get_service)):
    try:
        result = svc.cancel_reservation(res_id)
        return result
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100), svc: CommercService = Depends(get_service)):
    try:
        result = svc.list_orders(skip, limit)
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
