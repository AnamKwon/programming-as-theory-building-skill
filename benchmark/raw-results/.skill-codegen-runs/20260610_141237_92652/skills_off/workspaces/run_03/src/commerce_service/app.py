"""FastAPI application and routes."""
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session

from commerce_service.models import (
    SKUCreateRequest,
    StockAdjustRequest,
    ReservationCreateRequest,
    ReservationResponse,
    OrderResponse,
    PaginatedOrders,
    HealthResponse,
)
from commerce_service.repository import Database
from commerce_service.service import CommerceService
from commerce_service.security import verify_api_token


app = FastAPI(title="Commerce Service")
db = Database()


def get_session() -> Session:
    session = db.get_session()
    try:
        yield session
    finally:
        session.close()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: SKUCreateRequest,
    session: Session = Depends(get_session),
    token: str = Depends(verify_api_token),
):
    try:
        service = CommerceService(session)
        result = service.create_sku(request.sku, request.initial_stock)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust")
async def adjust_stock(
    request: StockAdjustRequest,
    session: Session = Depends(get_session),
    token: str = Depends(verify_api_token),
):
    try:
        service = CommerceService(session)
        result = service.adjust_stock(request.sku, request.amount)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(
    request: ReservationCreateRequest,
    session: Session = Depends(get_session),
    token: str = Depends(verify_api_token),
):
    try:
        service = CommerceService(session)
        result, status_code = service.create_reservation(
            request.sku, request.quantity, request.idempotency_key
        )
        return ReservationResponse(**result)
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: int,
    session: Session = Depends(get_session),
    token: str = Depends(verify_api_token),
):
    try:
        service = CommerceService(session)
        result = service.confirm_reservation(reservation_id)
        return result
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "Cannot confirm" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int,
    session: Session = Depends(get_session),
    token: str = Depends(verify_api_token),
):
    try:
        service = CommerceService(session)
        result = service.cancel_reservation(reservation_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=PaginatedOrders)
async def list_orders(
    page: int = 1,
    size: int = 10,
    session: Session = Depends(get_session),
):
    service = CommerceService(session)
    result = service.list_orders(page, size)
    return PaginatedOrders(
        items=[OrderResponse(**item) for item in result["items"]],
        page=result["page"],
        size=result["size"],
        total=result["total"],
    )
