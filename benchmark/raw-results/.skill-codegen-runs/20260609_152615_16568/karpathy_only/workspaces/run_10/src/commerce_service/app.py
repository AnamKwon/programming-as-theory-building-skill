"""FastAPI application for commerce service."""

from fastapi import Depends, FastAPI, HTTPException, Query, status

from .models import (
    AdjustStockRequest,
    AdjustStockResponse,
    CancelReservationResponse,
    ConfirmReservationResponse,
    CreateReservationRequest,
    CreateReservationResponse,
    CreateSKURequest,
    CreateSKUResponse,
    OrderListResponse,
    OrderResponse,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    CommerceService,
    IdempotencyError,
    InsufficientStockError,
    ReservationAlreadyConfirmedError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

# Initialize repository and service (in-memory SQLite for this example)
repo = Repository(":memory:")
service = CommerceService(repo)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/skus", response_model=CreateSKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key),
):
    """Create a new SKU."""
    try:
        sku = service.create_sku(request.sku_id, request.quantity)
        return CreateSKUResponse(sku_id=sku.id, quantity=sku.quantity)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.patch("/skus/{sku_id}/stock", response_model=AdjustStockResponse)
async def adjust_stock(
    sku_id: str,
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key),
):
    """Adjust stock for a SKU."""
    try:
        sku = service.adjust_stock(sku_id, request.quantity_delta)
        return AdjustStockResponse(sku_id=sku.id, quantity=sku.quantity)
    except SKUNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU {sku_id} not found",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations", response_model=CreateReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key),
):
    """Create a new reservation."""
    try:
        reservation = service.create_reservation(
            request.sku_id,
            request.quantity,
            request.idempotency_key,
        )
        return CreateReservationResponse(
            reservation_id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            state=reservation.state,
            expires_at=reservation.expires_at,
        )
    except SKUNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU {request.sku_id} not found",
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
            headers={"X-Error-Code": "INSUFFICIENT_STOCK"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/confirm", response_model=ConfirmReservationResponse)
async def confirm_reservation(
    reservation_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Confirm a reservation and create an order."""
    try:
        order = service.confirm_reservation(reservation_id)
        return ConfirmReservationResponse(
            order_id=order.id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            state="CONFIRMED",
        )
    except ReservationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found",
        )
    except ReservationExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e),
            headers={"X-Error-Code": "RESERVATION_EXPIRED"},
        )
    except ReservationAlreadyConfirmedError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
            headers={"X-Error-Code": "RESERVATION_ALREADY_CONFIRMED"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/cancel", response_model=CancelReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Cancel a reservation and release stock."""
    try:
        reservation = service.cancel_reservation(reservation_id)
        return CancelReservationResponse(
            reservation_id=reservation.id,
            state=reservation.state,
        )
    except ReservationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found",
        )
    except ReservationAlreadyConfirmedError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
            headers={"X-Error-Code": "CANNOT_CANCEL_CONFIRMED"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    api_key: str = Depends(verify_api_key),
):
    """List orders with pagination."""
    total, orders = service.list_orders(limit, offset)
    return OrderListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[
            OrderResponse(
                id=order.id,
                sku_id=order.sku_id,
                quantity=order.quantity,
                reservation_id=order.reservation_id,
                created_at=order.created_at,
            )
            for order in orders
        ],
    )


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Get order details."""
    order = service.get_order(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found",
        )

    return OrderResponse(
        id=order.id,
        sku_id=order.sku_id,
        quantity=order.quantity,
        reservation_id=order.reservation_id,
        created_at=order.created_at,
    )
