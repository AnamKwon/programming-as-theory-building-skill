from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session

from .models import (
    AdjustStockRequest,
    ConfirmReservationRequest,
    CreateReservationRequest,
    CreateSKURequest,
    ErrorResponse,
    OrderListResponse,
    OrderResponse,
    ReservationResponse,
    SKUResponse,
)
from .repository import Repository
from .security import verify_api_key
from .service import CommerceService

app = FastAPI(title="Commerce Service", version="0.1.0")
repository = Repository()
service = CommerceService(repository)


def get_session() -> Session:
    session = repository.get_session()
    try:
        yield session
    finally:
        session.close()


# Health check


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


# SKU endpoints


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED, tags=["sku"])
async def create_sku(
    request: CreateSKURequest, session: Session = Depends(get_session), _=Depends(verify_api_key)
):
    try:
        sku = service.create_sku(session, request.sku_id, request.stock)
        return SKUResponse(
            sku_id=sku.id,
            total_stock=sku.total_stock,
            available_stock=sku.available_stock,
            reserved_stock=sku.reserved_stock,
            sold_stock=sku.sold_stock,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post(
    "/skus/{sku_id}/adjust", response_model=SKUResponse, tags=["sku"]
)
async def adjust_stock(
    sku_id: str,
    request: AdjustStockRequest,
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    try:
        sku = service.adjust_stock(session, sku_id, request.delta)
        return SKUResponse(
            sku_id=sku.id,
            total_stock=sku.total_stock,
            available_stock=sku.available_stock,
            reserved_stock=sku.reserved_stock,
            sold_stock=sku.sold_stock,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Reservation endpoints


@app.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["reservation"],
)
async def create_reservation(
    request: CreateReservationRequest,
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    try:
        reservation = service.create_reservation(
            session, request.sku_id, request.quantity, request.idempotency_key
        )
        return ReservationResponse(
            reservation_id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=reservation.status,
            expires_at=reservation.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=OrderResponse,
    tags=["reservation"],
)
async def confirm_reservation(
    reservation_id: str,
    _request: ConfirmReservationRequest,
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    try:
        order = service.confirm_reservation(session, reservation_id)
        return OrderResponse(
            order_id=order.id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            status=order.status,
            created_at=order.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse, tags=["reservation"])
async def cancel_reservation(
    reservation_id: str,
    session: Session = Depends(get_session),
    __=Depends(verify_api_key),
):
    try:
        reservation = service.cancel_reservation(session, reservation_id)
        return ReservationResponse(
            reservation_id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=reservation.status,
            expires_at=reservation.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Order endpoints


@app.get("/orders/{order_id}", response_model=OrderResponse, tags=["order"])
async def get_order(order_id: str, session: Session = Depends(get_session)):
    order = service.get_order(session, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return OrderResponse(
        order_id=order.id,
        sku_id=order.sku_id,
        quantity=order.quantity,
        status=order.status,
        created_at=order.created_at,
    )


@app.get("/orders", response_model=OrderListResponse, tags=["order"])
async def list_orders(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), session: Session = Depends(get_session)
):
    try:
        orders, total = service.list_orders(session, page=page, page_size=page_size)
        return OrderListResponse(
            orders=[
                OrderResponse(
                    order_id=order.id,
                    sku_id=order.sku_id,
                    quantity=order.quantity,
                    status=order.status,
                    created_at=order.created_at,
                )
                for order in orders
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def main():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
