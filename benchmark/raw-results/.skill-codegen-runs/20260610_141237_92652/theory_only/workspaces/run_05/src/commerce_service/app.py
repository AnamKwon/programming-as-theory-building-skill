from fastapi import FastAPI, Depends, HTTPException, status, Query
from commerce_service.models import (
    CreateSKURequest,
    SKUResponse,
    AdjustStockRequest,
    AdjustStockResponse,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
    HealthResponse,
)
from commerce_service.repository import Repository, init_db
from commerce_service.service import Service
from commerce_service.security import verify_api_key


app = FastAPI()


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
def create_sku(
    request: CreateSKURequest, _: str = Depends(verify_api_key)
) -> SKUResponse:
    repo = Repository()
    service = Service(repo)
    result = service.create_sku(request.sku, request.initial_stock)
    repo.close()

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SKU already exists",
        )

    return SKUResponse(
        sku=result["sku"],
        available_stock=result["available_stock"],
    )


@app.post("/stock/adjust", response_model=AdjustStockResponse)
def adjust_stock(
    request: AdjustStockRequest, _: str = Depends(verify_api_key)
) -> AdjustStockResponse:
    repo = Repository()
    service = Service(repo)
    result = service.adjust_stock(request.sku, request.amount)
    repo.close()

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SKU not found",
        )

    return AdjustStockResponse(
        sku=result["sku"],
        available_stock=result["available_stock"],
    )


@app.post("/reservations", status_code=201)
def create_reservation(
    request: CreateReservationRequest, _: str = Depends(verify_api_key)
) -> ReservationResponse:
    repo = Repository()
    service = Service(repo)
    result, status_code = service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )
    repo.close()

    if status_code == "insufficient_stock":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient stock",
        )
    elif status_code == "sku_not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SKU not found",
        )
    elif result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create reservation",
        )

    return ReservationResponse(
        id=result["id"],
        sku=result["sku"],
        quantity=result["quantity"],
        status=result["status"],
        created_at=result["created_at"],
        idempotency_key=result["idempotency_key"],
    )


@app.post("/reservations/{id}/confirm", response_model=ReservationResponse)
def confirm_reservation(
    id: int, _: str = Depends(verify_api_key)
) -> ReservationResponse:
    repo = Repository()
    service = Service(repo)
    result, status_code = service.confirm_reservation(id)
    repo.close()

    if status_code == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )
    elif status_code == "invalid_state":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation is not in PENDING state",
        )
    elif status_code == "expired":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation expired",
        )
    elif result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to confirm reservation",
        )

    reservation = result[0] if isinstance(result, tuple) else result
    return ReservationResponse(
        id=reservation["id"],
        sku=reservation["sku"],
        quantity=reservation["quantity"],
        status=reservation["status"],
        created_at=reservation["created_at"],
        idempotency_key=reservation["idempotency_key"],
    )


@app.post("/reservations/{id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    id: int, _: str = Depends(verify_api_key)
) -> ReservationResponse:
    repo = Repository()
    service = Service(repo)
    result, status_code = service.cancel_reservation(id)
    repo.close()

    if status_code == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )
    elif status_code == "invalid_state":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation is not in PENDING state",
        )
    elif result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to cancel reservation",
        )

    return ReservationResponse(
        id=result["id"],
        sku=result["sku"],
        quantity=result["quantity"],
        status=result["status"],
        created_at=result["created_at"],
        idempotency_key=result["idempotency_key"],
    )


@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    _: str = Depends(verify_api_key)
) -> OrderListResponse:
    repo = Repository()
    orders, total = repo.list_orders(page, size)
    repo.close()

    return OrderListResponse(
        page=page,
        size=size,
        total=total,
        orders=[
            OrderResponse(
                id=order["id"],
                reservation_id=order["reservation_id"],
                created_at=order["created_at"],
            )
            for order in orders
        ],
    )
