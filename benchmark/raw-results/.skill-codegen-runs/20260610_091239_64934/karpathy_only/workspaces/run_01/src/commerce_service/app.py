"""FastAPI application."""

import os

from fastapi import Depends, FastAPI, Query

from .models import (
    OrderListResponse,
    OrderResponse,
    ReservationCancel,
    ReservationConfirm,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustment,
)
from .repository import Repository
from .security import verify_api_key
from .service import CommerceService


def create_app(db_path: str = ":memory:") -> FastAPI:
    app = FastAPI(title="Commerce Service", version="0.1.0")
    repository = Repository(db_path=db_path)
    service = CommerceService(repository)

    @app.get("/health")
    async def health_check() -> dict:
        """Service health check."""
        return {"status": "ok"}

    @app.post("/skus", response_model=SKUResponse)
    async def create_sku(
        payload: SKUCreate,
        api_key: str = Depends(verify_api_key),
    ) -> dict:
        """Create a new SKU."""
        return service.create_sku(payload.name, payload.price)

    @app.post("/stock/{sku_id}/adjust")
    async def adjust_stock(
        sku_id: int,
        payload: StockAdjustment,
        api_key: str = Depends(verify_api_key),
    ) -> dict:
        """Adjust stock quantity for a SKU."""
        return service.adjust_stock(sku_id, payload.quantity)

    @app.post("/reservations", response_model=ReservationResponse)
    async def create_reservation(
        payload: ReservationCreate,
        api_key: str = Depends(verify_api_key),
    ) -> dict:
        """Create a reservation."""
        return service.create_reservation(
            payload.sku_id,
            payload.quantity,
            payload.idempotency_key,
        )

    @app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
    async def confirm_reservation(
        reservation_id: int,
        payload: ReservationConfirm = None,
        api_key: str = Depends(verify_api_key),
    ) -> dict:
        """Confirm a reservation."""
        return service.confirm_reservation(reservation_id)

    @app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
    async def cancel_reservation(
        reservation_id: int,
        payload: ReservationCancel = None,
        api_key: str = Depends(verify_api_key),
    ) -> dict:
        """Cancel a reservation."""
        return service.cancel_reservation(reservation_id)

    @app.get("/orders", response_model=OrderListResponse)
    async def list_orders(
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        api_key: str = Depends(verify_api_key),
    ) -> dict:
        """List orders with pagination."""
        return service.list_orders(skip=skip, limit=limit)

    return app


db_path = os.getenv("DB_PATH", ":memory:")
app = create_app(db_path=db_path)


@app.get("/health")
async def health_check() -> dict:
    """Service health check."""
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse)
async def create_sku(
    payload: SKUCreate,
    api_key: str = Depends(verify_api_key),
) -> dict:
    """Create a new SKU."""
    return service.create_sku(payload.name, payload.price)


@app.post("/stock/{sku_id}/adjust")
async def adjust_stock(
    sku_id: int,
    payload: StockAdjustment,
    api_key: str = Depends(verify_api_key),
) -> dict:
    """Adjust stock quantity for a SKU."""
    return service.adjust_stock(sku_id, payload.quantity)


@app.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    payload: ReservationCreate,
    api_key: str = Depends(verify_api_key),
) -> dict:
    """Create a reservation."""
    return service.create_reservation(
        payload.sku_id,
        payload.quantity,
        payload.idempotency_key,
    )


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    payload: ReservationConfirm = None,
    api_key: str = Depends(verify_api_key),
) -> dict:
    """Confirm a reservation."""
    return service.confirm_reservation(reservation_id)


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    payload: ReservationCancel = None,
    api_key: str = Depends(verify_api_key),
) -> dict:
    """Cancel a reservation."""
    return service.cancel_reservation(reservation_id)


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    api_key: str = Depends(verify_api_key),
) -> dict:
    """List orders with pagination."""
    return service.list_orders(skip=skip, limit=limit)
