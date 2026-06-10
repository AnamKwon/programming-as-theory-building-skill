from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from . import models
from .repository import OrderRepository, ReservationRepository, SKURepository


class SKUService:
    def __init__(self, session: AsyncSession):
        self.repo = SKURepository(session)

    async def create_sku(self, sku: str, stock: int) -> models.SKURecord:
        return await self.repo.create(sku, stock)

    async def adjust_stock(self, sku: str, delta: int) -> models.SKURecord:
        record = await self.repo.get_by_sku(sku)
        if not record:
            raise ValueError(f"SKU not found: {sku}")
        if record.stock + delta < 0:
            raise ValueError("Insufficient stock for adjustment")
        return await self.repo.update_stock(record.id, delta)


class ReservationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.sku_repo = SKURepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.order_repo = OrderRepository(session)

    async def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str,
        ttl_seconds: int,
    ) -> models.ReservationRecord:
        existing = await self.reservation_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku_record = await self.sku_repo.get_by_sku(sku)
        if not sku_record:
            raise ValueError(f"SKU not found: {sku}")

        if sku_record.stock < quantity:
            raise ValueError("Insufficient stock")

        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        reservation = await self.reservation_repo.create(
            sku_id=sku_record.id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )

        await self.sku_repo.update_stock(sku_record.id, -quantity)

        return reservation

    async def confirm_reservation(self, reservation_id: int) -> models.OrderRecord:
        reservation = await self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        if reservation.status == models.ReservationStatus.EXPIRED:
            raise ValueError("Reservation has expired")

        if reservation.status == models.ReservationStatus.CANCELLED:
            raise ValueError("Reservation has been cancelled")

        if reservation.status == models.ReservationStatus.CONFIRMED:
            sku_record = await self.sku_repo.get_by_id(reservation.sku_id)
            if not sku_record:
                raise ValueError("SKU not found")
            order = await self.order_repo.create(
                reservation_id=reservation_id,
                sku=sku_record.sku,
                quantity=reservation.quantity,
            )
            return order

        if reservation.expires_at < datetime.utcnow():
            await self.reservation_repo.update_status(
                reservation_id, models.ReservationStatus.EXPIRED
            )
            sku_record = await self.sku_repo.get_by_id(reservation.sku_id)
            if sku_record:
                await self.sku_repo.update_stock(sku_record.id, reservation.quantity)
            raise ValueError("Reservation has expired")

        await self.reservation_repo.update_status(
            reservation_id, models.ReservationStatus.CONFIRMED
        )

        sku_record = await self.sku_repo.get_by_id(reservation.sku_id)
        if not sku_record:
            raise ValueError("SKU not found")

        order = await self.order_repo.create(
            reservation_id=reservation_id,
            sku=sku_record.sku,
            quantity=reservation.quantity,
        )

        return order

    async def cancel_reservation(self, reservation_id: int) -> models.ReservationRecord:
        reservation = await self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        if reservation.status not in (
            models.ReservationStatus.PENDING,
            models.ReservationStatus.CONFIRMED,
        ):
            raise ValueError("Cannot cancel reservation in current state")

        sku_record = await self.sku_repo.get_by_id(reservation.sku_id)
        if sku_record:
            await self.sku_repo.update_stock(sku_record.id, reservation.quantity)

        return await self.reservation_repo.update_status(
            reservation_id, models.ReservationStatus.CANCELLED
        )


class OrderService:
    def __init__(self, session: AsyncSession):
        self.repo = OrderRepository(session)

    async def get_order(self, order_id: int) -> models.OrderRecord:
        order = await self.repo.get_by_id(order_id)
        if not order:
            raise ValueError("Order not found")
        return order

    async def list_orders(
        self, limit: int, offset: int
    ) -> tuple[list[models.OrderRecord], int]:
        return await self.repo.list_orders(limit, offset)
