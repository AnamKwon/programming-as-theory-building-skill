from fastapi import FastAPI, HTTPException, status, Query
from fastapi.responses import JSONResponse

from .models import (
    SKU, SKUCreate, StockAdjustment,
    Reservation, ReservationCreate,
    Order, OrderResponse, ErrorResponse
)
from .repository import Repository
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationAlreadyExistsError,
    InvalidReservationStateError
)
from .security import APIKeyDependency

app = FastAPI(title="Commerce Service", version="1.0.0")
repo = Repository()
service = CommerceService(repo)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/skus", response_model=SKU)
async def create_sku(sku: SKUCreate, _: APIKeyDependency):
    sku_id = service.create_sku(sku.name, sku.quantity)
    sku_data = repo.get_sku(sku_id)
    return SKU(**sku_data)


@app.get("/skus/{sku_id}", response_model=SKU)
async def get_sku(sku_id: int):
    sku_data = service.get_sku(sku_id)
    if not sku_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU {sku_id} not found"
        )
    return SKU(**sku_data)


@app.post("/skus/{sku_id}/adjust", response_model=SKU)
async def adjust_stock(sku_id: int, adjustment: StockAdjustment, _: APIKeyDependency):
    try:
        service.adjust_stock(sku_id, adjustment.adjustment)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    sku_data = repo.get_sku(sku_id)
    return SKU(**sku_data)


@app.post("/reservations", response_model=Reservation)
async def create_reservation(req: ReservationCreate, _: APIKeyDependency):
    try:
        reservation_id = service.create_reservation(
            req.sku_id,
            req.quantity,
            req.expires_in_seconds,
            req.idempotency_key
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except ReservationAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )

    reservation = repo.get_reservation(reservation_id)
    return Reservation(**reservation)


@app.get("/reservations/{reservation_id}", response_model=Reservation)
async def get_reservation(reservation_id: int):
    reservation = service.get_reservation(reservation_id)
    if not reservation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found"
        )
    return Reservation(**reservation)


@app.post("/reservations/{reservation_id}/confirm", response_model=Order)
async def confirm_reservation(reservation_id: int, _: APIKeyDependency):
    try:
        service.confirm_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except InvalidReservationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )

    reservation = repo.get_reservation(reservation_id)
    # Get the order created by confirming this reservation
    # The order is found via the reservation being added to order_items
    orders, _ = repo.list_orders(skip=0, limit=100)
    for order in orders:
        for item in order["items"]:
            if item["reservation_id"] == reservation_id:
                return Order(**order)

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Order not found after confirmation"
    )


@app.post("/reservations/{reservation_id}/cancel", response_model=Reservation)
async def cancel_reservation(reservation_id: int, _: APIKeyDependency):
    try:
        service.cancel_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except InvalidReservationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )

    reservation = repo.get_reservation(reservation_id)
    return Reservation(**reservation)


@app.get("/orders", response_model=OrderResponse)
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100)
):
    orders, total = service.list_orders(skip, limit)
    return OrderResponse(
        orders=[Order(**order) for order in orders],
        total=total,
        skip=skip,
        limit=limit
    )


@app.get("/orders/{order_id}", response_model=Order)
async def get_order(order_id: int):
    order = service.get_order(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found"
        )
    return Order(**order)
