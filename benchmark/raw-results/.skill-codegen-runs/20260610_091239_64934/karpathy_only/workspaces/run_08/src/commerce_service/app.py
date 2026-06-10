import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from . import models
from .security import verify_api_key
from .service import OrderService, ReservationService, SKUService

database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///commerce.db")

engine = create_async_engine(database_url, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Commerce Service", lifespan=lifespan)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.commit()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/skus", dependencies=[Depends(verify_api_key)])
async def create_sku(
    req: models.SKUCreate,
    session: AsyncSession = Depends(get_session),
):
    try:
        sku_service = SKUService(session)
        result = await sku_service.create_sku(req.sku, req.stock)
        return models.SKUResponse(id=result.id, sku=result.sku, stock=result.stock)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/skus/{sku}/stock", dependencies=[Depends(verify_api_key)])
async def adjust_stock(
    sku: str,
    req: models.StockAdjustment,
    session: AsyncSession = Depends(get_session),
):
    try:
        sku_service = SKUService(session)
        result = await sku_service.adjust_stock(sku, req.delta)
        return models.SKUResponse(id=result.id, sku=result.sku, stock=result.stock)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", dependencies=[Depends(verify_api_key)])
async def create_reservation(
    req: models.ReservationRequest,
    session: AsyncSession = Depends(get_session),
):
    try:
        service = ReservationService(session)
        result = await service.create_reservation(
            sku=req.sku,
            quantity=req.quantity,
            idempotency_key=req.idempotency_key,
            ttl_seconds=req.ttl_seconds,
        )
        return models.ReservationResponse(
            id=result.id,
            sku=req.sku,
            quantity=result.quantity,
            status=result.status,
            expires_at=result.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", dependencies=[Depends(verify_api_key)])
async def confirm_reservation(
    reservation_id: int,
    session: AsyncSession = Depends(get_session),
):
    try:
        service = ReservationService(session)
        order = await service.confirm_reservation(reservation_id)
        return models.OrderResponse(
            id=order.id,
            sku=order.sku,
            quantity=order.quantity,
            created_at=order.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete(
    "/reservations/{reservation_id}", dependencies=[Depends(verify_api_key)]
)
async def cancel_reservation(
    reservation_id: int,
    session: AsyncSession = Depends(get_session),
):
    try:
        service = ReservationService(session)
        result = await service.cancel_reservation(reservation_id)
        return models.ReservationResponse(
            id=result.id,
            sku="",
            quantity=result.quantity,
            status=result.status,
            expires_at=result.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders")
async def list_orders(
    limit: int = 10,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    try:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be non-negative")

        service = OrderService(session)
        items, total = await service.list_orders(limit, offset)
        return models.OrderListResponse(
            items=[
                models.OrderResponse(
                    id=item.id,
                    sku=item.sku,
                    quantity=item.quantity,
                    created_at=item.created_at,
                )
                for item in items
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders/{order_id}")
async def get_order(
    order_id: int,
    session: AsyncSession = Depends(get_session),
):
    try:
        service = OrderService(session)
        order = await service.get_order(order_id)
        return models.OrderResponse(
            id=order.id,
            sku=order.sku,
            quantity=order.quantity,
            created_at=order.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
