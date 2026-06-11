from fastapi import FastAPI, Depends, status
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.security import verify_api_key
from commerce_service.models import (
    HealthResponse, SKUCreate, SKUResponse, StockAdjustRequest,
    ReservationCreate, ReservationResponse, OrderListResponse
)

app = FastAPI(title="Commerce Inventory & Order API")
repo = Repository()
service = CommerceService(repo)


@app.on_event("startup")
async def startup_event():
    repo.init_db()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(request: SKUCreate, api_key: str = Depends(verify_api_key)):
    return service.create_sku(request)


@app.post("/stock/adjust")
async def adjust_stock(request: StockAdjustRequest, api_key: str = Depends(verify_api_key)):
    return service.adjust_stock(request)


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(request: ReservationCreate, api_key: str = Depends(verify_api_key)):
    return service.create_reservation(request)


@app.post("/reservations/{id}/confirm")
async def confirm_reservation(id: int, api_key: str = Depends(verify_api_key)):
    return service.confirm_reservation(id)


@app.post("/reservations/{id}/cancel")
async def cancel_reservation(id: int, api_key: str = Depends(verify_api_key)):
    return service.cancel_reservation(id)


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(page: int = 1, size: int = 10):
    return service.get_orders(page, size)
