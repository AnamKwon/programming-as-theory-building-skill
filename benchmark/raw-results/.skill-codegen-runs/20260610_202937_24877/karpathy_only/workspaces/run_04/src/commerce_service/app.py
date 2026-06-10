from fastapi import FastAPI, Depends, status
from sqlalchemy.orm import Session
from .repository import SessionLocal, init_db
from .service import CommerceService
from .security import verify_api_key
from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrdersListResponse,
)

app = FastAPI(title="Commerce Service")


@app.on_event("startup")
def startup_event():
    init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    from .repository import Repository
    repo = Repository(db)
    return CommerceService(repo)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    sku = service.create_sku(request.sku, request.initial_stock)
    return {"id": sku.id, "sku": sku.sku, "stock": sku.stock}


@app.post("/stock/adjust", status_code=status.HTTP_200_OK)
async def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    sku = service.adjust_stock(request.sku, request.amount)
    return {"sku": sku.sku, "stock": sku.stock}


@app.post("/reservations", status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
) -> ReservationResponse:
    return service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )


@app.post("/reservations/{reservation_id}/confirm", status_code=status.HTTP_200_OK)
async def confirm_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
) -> ReservationResponse:
    return service.confirm_reservation(reservation_id)


@app.post("/reservations/{reservation_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
) -> ReservationResponse:
    return service.cancel_reservation(reservation_id)


@app.get("/orders", status_code=status.HTTP_200_OK)
async def get_orders(
    page: int = 1,
    size: int = 10,
    api_key: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
) -> OrdersListResponse:
    return service.get_orders(page, size)
