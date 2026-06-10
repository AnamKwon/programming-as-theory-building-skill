from fastapi import Depends, FastAPI, HTTPException, Query, status

from commerce_service.models import (
    AdjustStockRequest,
    CancelReservationRequest,
    ConfirmReservationRequest,
    CreateOrderRequest,
    CreateReservationRequest,
    CreateSKURequest,
    HealthResponse,
    OrderListResponse,
    OrderResponse,
    ReservationResponse,
    SKUResponse,
    StockAdjustmentResponse,
)
from commerce_service.repository import Repository
from commerce_service.security import api_key_header, verify_api_key
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    OrderNotFoundError,
    ReservationExpiredError,
    ReservationNotFoundError,
    ReservationStateError,
    ServiceError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

# Global repository and service instances
_repo: Repository = None
_service: CommerceService = None


def get_repository() -> Repository:
    global _repo
    if _repo is None:
        _repo = Repository()
    return _repo


def get_service() -> CommerceService:
    global _service
    if _service is None:
        _service = CommerceService(get_repository())
    return _service


@app.on_event("startup")
def startup():
    get_repository()
    get_service()


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse()


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(api_key_header),
) -> SKUResponse:
    verify_api_key(api_key)

    try:
        sku = get_service().create_sku(request.sku_id, request.initial_stock)
        return SKUResponse(
            sku_id=sku.sku_id,
            available_stock=sku.available_stock,
            reserved_stock=sku.reserved_stock,
        )
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/skus/{sku_id}", response_model=SKUResponse)
async def get_sku(sku_id: str) -> SKUResponse:
    try:
        sku = get_service().get_sku(sku_id)
        return SKUResponse(
            sku_id=sku.sku_id,
            available_stock=sku.available_stock,
            reserved_stock=sku.reserved_stock,
        )
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post(
    "/skus/{sku_id}/adjust-stock",
    response_model=StockAdjustmentResponse,
)
async def adjust_stock(
    sku_id: str,
    request: AdjustStockRequest,
    api_key: str = Depends(api_key_header),
) -> StockAdjustmentResponse:
    verify_api_key(api_key)

    try:
        sku = get_service().adjust_stock(sku_id, request.adjustment)
        return StockAdjustmentResponse(
            sku_id=sku.sku_id,
            available_stock=sku.available_stock,
            reserved_stock=sku.reserved_stock,
        )
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(api_key_header),
) -> ReservationResponse:
    verify_api_key(api_key)

    try:
        reservation = get_service().create_reservation(
            request.sku_id,
            request.quantity,
            request.idempotency_key,
            request.ttl_seconds,
        )
        return ReservationResponse(
            reservation_id=reservation.reservation_id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            state=reservation.state,
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
        )
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/reservations/{reservation_id}", response_model=ReservationResponse)
async def get_reservation(reservation_id: str) -> ReservationResponse:
    try:
        reservation = get_service().repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")
        return ReservationResponse(
            reservation_id=reservation.reservation_id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            state=reservation.state,
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
        )
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: str,
    request: ConfirmReservationRequest,
    api_key: str = Depends(api_key_header),
) -> ReservationResponse:
    verify_api_key(api_key)

    try:
        reservation = get_service().confirm_reservation(
            reservation_id, request.idempotency_key
        )
        return ReservationResponse(
            reservation_id=reservation.reservation_id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            state=reservation.state,
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
        )
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ReservationStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    request: CancelReservationRequest,
    api_key: str = Depends(api_key_header),
) -> ReservationResponse:
    verify_api_key(api_key)

    try:
        reservation = get_service().cancel_reservation(reservation_id)
        return ReservationResponse(
            reservation_id=reservation.reservation_id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            state=reservation.state,
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
        )
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    request: CreateOrderRequest,
    api_key: str = Depends(api_key_header),
) -> OrderResponse:
    verify_api_key(api_key)

    try:
        order = get_service().create_order(request.reservation_ids, request.idempotency_key)
        return OrderResponse(
            order_id=order.order_id,
            reservation_ids=order.reservation_ids,
            state=order.state,
            created_at=order.created_at,
        )
    except (ReservationNotFoundError, ReservationStateError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str) -> OrderResponse:
    try:
        order = get_service().get_order(order_id)
        return OrderResponse(
            order_id=order.order_id,
            reservation_ids=order.reservation_ids,
            state=order.state,
            created_at=order.created_at,
        )
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> OrderListResponse:
    orders, total = get_service().list_orders(page, page_size)
    return OrderListResponse(
        orders=[
            OrderResponse(
                order_id=order.order_id,
                reservation_ids=order.reservation_ids,
                state=order.state,
                created_at=order.created_at,
            )
            for order in orders
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
