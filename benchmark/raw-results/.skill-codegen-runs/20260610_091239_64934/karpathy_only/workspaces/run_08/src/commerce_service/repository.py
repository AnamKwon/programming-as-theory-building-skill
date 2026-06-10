from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from . import models


class SKURepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, sku: str, stock: int) -> models.SKURecord:
        record = models.SKURecord(sku=sku, stock=stock)
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_sku(self, sku: str) -> Optional[models.SKURecord]:
        result = await self.session.execute(
            select(models.SKURecord).where(models.SKURecord.sku == sku)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, id: int) -> Optional[models.SKURecord]:
        result = await self.session.execute(
            select(models.SKURecord).where(models.SKURecord.id == id)
        )
        return result.scalar_one_or_none()

    async def update_stock(self, id: int, delta: int) -> Optional[models.SKURecord]:
        record = await self.get_by_id(id)
        if record:
            record.stock += delta
            await self.session.flush()
        return record


class ReservationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> models.ReservationRecord:
        record = models.ReservationRecord(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status=models.ReservationStatus.PENDING,
            expires_at=expires_at,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_id(self, id: int) -> Optional[models.ReservationRecord]:
        result = await self.session.execute(
            select(models.ReservationRecord).where(models.ReservationRecord.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(
        self, key: str
    ) -> Optional[models.ReservationRecord]:
        result = await self.session.execute(
            select(models.ReservationRecord).where(
                models.ReservationRecord.idempotency_key == key
            )
        )
        return result.scalar_one_or_none()

    async def update_status(
        self, id: int, status: models.ReservationStatus
    ) -> Optional[models.ReservationRecord]:
        record = await self.get_by_id(id)
        if record:
            record.status = status
            if status == models.ReservationStatus.CONFIRMED:
                record.confirmed_at = datetime.utcnow()
            await self.session.flush()
        return record


class OrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, reservation_id: int, sku: str, quantity: int
    ) -> models.OrderRecord:
        record = models.OrderRecord(
            reservation_id=reservation_id,
            sku=sku,
            quantity=quantity,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_id(self, id: int) -> Optional[models.OrderRecord]:
        result = await self.session.execute(
            select(models.OrderRecord).where(models.OrderRecord.id == id)
        )
        return result.scalar_one_or_none()

    async def list_orders(
        self, limit: int, offset: int
    ) -> tuple[list[models.OrderRecord], int]:
        count_result = await self.session.execute(select(models.OrderRecord))
        total = len(count_result.scalars().all())

        result = await self.session.execute(
            select(models.OrderRecord).limit(limit).offset(offset)
        )
        items = result.scalars().all()
        return items, total
