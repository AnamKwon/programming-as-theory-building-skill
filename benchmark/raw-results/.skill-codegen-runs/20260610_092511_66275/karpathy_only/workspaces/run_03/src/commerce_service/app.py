from fastapi import FastAPI, Depends, HTTPException, Query, status

from commerce_service import __version__
from commerce_service.models import (
    AdjustStockRequest,
    CreateReservationRequest,
    CreateSKURequest,
    HealthResponse,
    OrderResponse,
    PaginatedOrdersResponse,
    ReservationResponse,
    SKUResponse,
)
from commerce_service.repository import Repository
from commerce_service.security import get_api_key
from commerce_service.service import (
    InsufficientStockError,
    ReservationAlreadyProcessedError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
)

app = FastAPI(title="Commerce Service", version=__version__)

_repository = Repository()


def get_repository() -> Repository:
    return _repository


def get_service(repository: Repository = Depends(get_repository)) -> Service:
    return Service(repository)


@app.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(status="ok", version=__version__)


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(get_api_key),
    svc: Service = Depends(get_service),
    repo: Repository = Depends(get_repository),
):
    if not svc.create_sku(request.sku, request.name, request.initial_stock):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="SKU already exists"
        )

    sku_data = repo.get_sku(request.sku)
    return SKUResponse(
        sku=sku_data["sku"],
        name=sku_data["name"],
        available_stock=sku_data["available_stock"],
        reserved_stock=sku_data["reserved_stock"],
    )


@app.post("/stock/adjust", status_code=status.HTTP_204_NO_CONTENT)
def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(get_api_key),
    svc: Service = Depends(get_service),
):
    try:
        svc.adjust_stock(request.sku, request.quantity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(get_api_key),
    svc: Service = Depends(get_service),
):
    try:
        result = svc.create_reservation(
            request.sku, request.quantity, request.idempotency_key
        )
        return ReservationResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ReservationAlreadyProcessedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
def confirm_reservation(
    reservation_id: str,
    api_key: str = Depends(get_api_key),
    svc: Service = Depends(get_service),
):
    try:
        result = svc.confirm_reservation(reservation_id)
        return OrderResponse(**result)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_reservation(
    reservation_id: str,
    api_key: str = Depends(get_api_key),
    svc: Service = Depends(get_service),
):
    try:
        svc.cancel_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/orders", response_model=PaginatedOrdersResponse)
def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    repo: Repository = Depends(get_repository),
):
    orders, total = repo.list_orders(skip=skip, limit=limit)
    return PaginatedOrdersResponse(
        orders=[
            OrderResponse(
                order_id=order["id"],
                sku=order["sku"],
                quantity=order["quantity"],
                status=order["status"],
                created_at=order["created_at"],
                updated_at=order["updated_at"],
            )
            for order in orders
        ],
        total=total,
        skip=skip,
        limit=limit,
    )
