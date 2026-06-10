import pytest
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service import models
from src.commerce_service.service import (
    OrderService,
    ReservationService,
    SKUService,
)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_sku(db_session: AsyncSession):
    service = SKUService(db_session)
    result = await service.create_sku("SKU-001", 100)
    assert result.sku == "SKU-001"
    assert result.stock == 100


@pytest.mark.asyncio
async def test_adjust_stock(db_session: AsyncSession):
    service = SKUService(db_session)
    sku = await service.create_sku("SKU-001", 100)

    result = await service.adjust_stock("SKU-001", -10)
    assert result.stock == 90

    result = await service.adjust_stock("SKU-001", 20)
    assert result.stock == 110


@pytest.mark.asyncio
async def test_adjust_stock_insufficient(db_session: AsyncSession):
    service = SKUService(db_session)
    await service.create_sku("SKU-001", 10)

    with pytest.raises(ValueError, match="Insufficient stock"):
        await service.adjust_stock("SKU-001", -20)


@pytest.mark.asyncio
async def test_create_reservation(db_session: AsyncSession):
    sku_service = SKUService(db_session)
    await sku_service.create_sku("SKU-001", 100)

    service = ReservationService(db_session)
    result = await service.create_reservation(
        sku="SKU-001",
        quantity=50,
        idempotency_key="idem-1",
        ttl_seconds=3600,
    )
    assert result.quantity == 50
    assert result.status == models.ReservationStatus.PENDING
    assert result.sku_id is not None


@pytest.mark.asyncio
async def test_create_reservation_insufficient_stock(db_session: AsyncSession):
    sku_service = SKUService(db_session)
    await sku_service.create_sku("SKU-001", 10)

    service = ReservationService(db_session)
    with pytest.raises(ValueError, match="Insufficient stock"):
        await service.create_reservation(
            sku="SKU-001",
            quantity=50,
            idempotency_key="idem-1",
            ttl_seconds=3600,
        )


@pytest.mark.asyncio
async def test_idempotent_reservation(db_session: AsyncSession):
    sku_service = SKUService(db_session)
    await sku_service.create_sku("SKU-001", 100)

    service = ReservationService(db_session)
    result1 = await service.create_reservation(
        sku="SKU-001",
        quantity=50,
        idempotency_key="idem-1",
        ttl_seconds=3600,
    )
    result2 = await service.create_reservation(
        sku="SKU-001",
        quantity=50,
        idempotency_key="idem-1",
        ttl_seconds=3600,
    )
    assert result1.id == result2.id


@pytest.mark.asyncio
async def test_confirm_reservation(db_session: AsyncSession):
    sku_service = SKUService(db_session)
    await sku_service.create_sku("SKU-001", 100)

    service = ReservationService(db_session)
    reservation = await service.create_reservation(
        sku="SKU-001",
        quantity=50,
        idempotency_key="idem-1",
        ttl_seconds=3600,
    )

    order = await service.confirm_reservation(reservation.id)
    assert order.sku == "SKU-001"
    assert order.quantity == 50

    updated_res = await service.reservation_repo.get_by_id(reservation.id)
    assert updated_res.status == models.ReservationStatus.CONFIRMED


@pytest.mark.asyncio
async def test_confirm_expired_reservation(db_session: AsyncSession):
    sku_service = SKUService(db_session)
    await sku_service.create_sku("SKU-001", 100)

    service = ReservationService(db_session)

    reservation = await service.reservation_repo.create(
        sku_id=1,
        quantity=50,
        idempotency_key="idem-1",
        expires_at=datetime.utcnow() - timedelta(seconds=1),
    )

    with pytest.raises(ValueError, match="Reservation has expired"):
        await service.confirm_reservation(reservation.id)


@pytest.mark.asyncio
async def test_cancel_reservation(db_session: AsyncSession):
    sku_service = SKUService(db_session)
    await sku_service.create_sku("SKU-001", 100)

    service = ReservationService(db_session)
    reservation = await service.create_reservation(
        sku="SKU-001",
        quantity=50,
        idempotency_key="idem-1",
        ttl_seconds=3600,
    )

    result = await service.cancel_reservation(reservation.id)
    assert result.status == models.ReservationStatus.CANCELLED

    sku = await service.sku_repo.get_by_id(1)
    assert sku.stock == 100


@pytest.mark.asyncio
async def test_list_orders_pagination(db_session: AsyncSession):
    sku_service = SKUService(db_session)
    await sku_service.create_sku("SKU-001", 100)

    res_service = ReservationService(db_session)
    for i in range(15):
        reservation = await res_service.create_reservation(
            sku="SKU-001",
            quantity=1,
            idempotency_key=f"idem-{i}",
            ttl_seconds=3600,
        )
        await res_service.confirm_reservation(reservation.id)

    order_service = OrderService(db_session)
    items, total = await order_service.list_orders(limit=10, offset=0)
    assert len(items) == 10
    assert total == 15

    items2, total2 = await order_service.list_orders(limit=10, offset=10)
    assert len(items2) == 5
    assert total2 == 15
