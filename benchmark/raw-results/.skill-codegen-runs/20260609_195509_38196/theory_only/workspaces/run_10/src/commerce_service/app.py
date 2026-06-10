from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from typing import Annotated

from .repository import init_db, get_session, Repository
from .service import (
    Service,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidStateTransitionError,
    IdempotencyConflictError,
)
from .security import verify_api_key
from .models import (
    CreateSKURequest,
    SKUResponse,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    OrdersListResponse,
    ErrorResponse,
)

app = FastAPI(title="Commerce Service")


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# SKU Management


@app.post(
    "/api/skus",
    response_model=SKUResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
    dependencies=[Depends(verify_api_key)],
)
async def create_sku(req: CreateSKURequest):
    with get_session() as session:
        repo = Repository(session)
        service = Service(repo)
        try:
            result = service.create_sku(req.name, req.quantity)
            return SKUResponse(**result)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get(
    "/api/skus/{sku_id}",
    response_model=SKUResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_sku(sku_id: int):
    with get_session() as session:
        repo = Repository(session)
        service = Service(repo)
        try:
            result = service.get_sku(sku_id)
            return SKUResponse(**result)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# Stock Management


@app.post(
    "/api/stock/{sku_id}/adjust",
    response_model=SKUResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
    dependencies=[Depends(verify_api_key)],
)
async def adjust_stock(sku_id: int, req: AdjustStockRequest):
    with get_session() as session:
        repo = Repository(session)
        service = Service(repo)
        try:
            result = service.adjust_stock(sku_id, req.delta)
            return SKUResponse(**result)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# Reservations


@app.post(
    "/api/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
    dependencies=[Depends(verify_api_key)],
)
async def create_reservation(req: CreateReservationRequest):
    with get_session() as session:
        repo = Repository(session)
        service = Service(repo)
        try:
            result = service.create_reservation(
                req.sku_id, req.quantity, req.idempotency_key
            )
            return ReservationResponse(**result)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except InsufficientStockError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except IdempotencyConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post(
    "/api/reservations/{reservation_id}/confirm",
    response_model=ReservationResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
    },
    dependencies=[Depends(verify_api_key)],
)
async def confirm_reservation(reservation_id: int):
    with get_session() as session:
        repo = Repository(session)
        service = Service(repo)
        try:
            result = service.confirm_reservation(reservation_id)
            return ReservationResponse(**result)
        except ReservationNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except ReservationExpiredError as e:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
        except InvalidStateTransitionError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post(
    "/api/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
    },
    dependencies=[Depends(verify_api_key)],
)
async def cancel_reservation(reservation_id: int):
    with get_session() as session:
        repo = Repository(session)
        service = Service(repo)
        try:
            result = service.cancel_reservation(reservation_id)
            return ReservationResponse(**result)
        except ReservationNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except InvalidStateTransitionError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Orders


@app.get(
    "/api/orders",
    response_model=OrdersListResponse,
    responses={400: {"model": ErrorResponse}},
)
async def list_orders(offset: int = 0, limit: int = 10):
    if offset < 0 or limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pagination parameters: offset >= 0, 1 <= limit <= 100",
        )
    with get_session() as session:
        repo = Repository(session)
        service = Service(repo)
        result = service.get_orders(offset, limit)
        return OrdersListResponse(**result)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )
