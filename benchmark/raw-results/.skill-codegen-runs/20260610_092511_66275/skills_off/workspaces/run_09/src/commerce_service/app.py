import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from .repository import Repository
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidStateTransitionError,
)
from .models import (
    CreateSkuRequest,
    CreateReservationRequest,
    StockAdjustmentRequest,
    SkuResponse,
    StockResponse,
    ReservationResponse,
    OrderResponse,
    PaginatedOrdersResponse,
    ErrorResponse,
)
from .security import verify_api_key


repository = Repository()
service = CommerceService(repository)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SkuResponse, dependencies=[Depends(verify_api_key)])
async def create_sku(req: CreateSkuRequest):
    try:
        sku = service.create_sku(req.code, req.name)
        return sku
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/stock/adjust", response_model=StockResponse, dependencies=[Depends(verify_api_key)])
async def adjust_stock(req: StockAdjustmentRequest):
    try:
        stock = service.adjust_stock(req.sku_id, req.quantity)
        return stock
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/reservations", response_model=OrderResponse, dependencies=[Depends(verify_api_key)])
async def create_reservation(req: CreateReservationRequest):
    try:
        order = service.create_reservation(req.sku_id, req.quantity, req.idempotency_key)
        return order
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse, dependencies=[Depends(verify_api_key)])
async def confirm_reservation(reservation_id: int):
    try:
        order = service.confirm_reservation(reservation_id)
        return order
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/reservations/{reservation_id}/cancel", response_model=OrderResponse, dependencies=[Depends(verify_api_key)])
async def cancel_reservation(reservation_id: int):
    try:
        order = service.cancel_reservation(reservation_id)
        return order
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/orders", response_model=PaginatedOrdersResponse, dependencies=[Depends(verify_api_key)])
async def list_orders(page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    try:
        result = service.get_orders(page=page, page_size=page_size)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/orders/{order_id}", response_model=OrderResponse, dependencies=[Depends(verify_api_key)])
async def get_order(order_id: int):
    try:
        order = service.get_order(order_id)
        return order
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


def run_server():
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
    )
