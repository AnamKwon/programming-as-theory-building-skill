from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .models import OrderModel, ReservationModel, SKUModel
from .repository import OrderRepository, ReservationRepository, SKURepository


class CommerceService:
    def __init__(self, db: Session):
        self.db = db
        self.skus = SKURepository(db)
        self.reservations = ReservationRepository(db)
        self.orders = OrderRepository(db)

    def create_sku(self, code: str, price, stock_quantity: int) -> SKUModel:
        existing = self.skus.get_by_code(code)
        if existing:
            raise ValueError(f"SKU with code {code} already exists")
        return self.skus.create(code, price, stock_quantity)

    def adjust_stock(self, sku_id: int, delta: int) -> SKUModel:
        sku = self.skus.get_by_id(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        new_stock = sku.stock_quantity + delta
        if new_stock < 0:
            raise ValueError("Stock cannot be negative")

        return self.skus.update_stock(sku_id, delta)

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        customer_id: str,
        ttl_seconds: int,
        idempotency_key: str | None = None,
    ) -> ReservationModel:
        # Idempotency: return existing if key was used
        if idempotency_key:
            existing = self.reservations.get_by_idempotency_key(idempotency_key)
            if existing and existing.status == "pending":
                return existing
            if existing and existing.status in ("confirmed", "cancelled"):
                raise ValueError(
                    f"Reservation with idempotency key already processed (status={existing.status})"
                )

        sku = self.skus.get_by_id(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        if sku.stock_quantity < quantity:
            raise ValueError(
                f"Insufficient stock: requested {quantity}, available {sku.stock_quantity}"
            )

        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        reservation = self.reservations.create(
            sku_id=sku_id,
            quantity=quantity,
            customer_id=customer_id,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

        self.skus.update_stock(sku_id, -quantity)

        return reservation

    def confirm_reservation(self, reservation_id: int) -> OrderModel:
        reservation = self.reservations.get_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "pending":
            raise ValueError(
                f"Cannot confirm reservation with status {reservation.status}"
            )

        if datetime.utcnow() > reservation.expires_at:
            self.reservations.update_status(reservation_id, "expired")
            self.skus.update_stock(reservation.sku_id, reservation.quantity)
            raise ValueError("Reservation has expired")

        self.reservations.update_status(reservation_id, "confirmed")

        order = self.orders.create(
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            customer_id=reservation.customer_id,
        )

        return order

    def cancel_reservation(self, reservation_id: int) -> ReservationModel:
        reservation = self.reservations.get_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "pending":
            raise ValueError(
                f"Cannot cancel reservation with status {reservation.status}"
            )

        self.reservations.update_status(reservation_id, "cancelled")
        self.skus.update_stock(reservation.sku_id, reservation.quantity)

        return reservation

    def list_orders(self, offset: int = 0, limit: int = 20) -> tuple[list[OrderModel], int]:
        return self.orders.list_paginated(offset, limit)
