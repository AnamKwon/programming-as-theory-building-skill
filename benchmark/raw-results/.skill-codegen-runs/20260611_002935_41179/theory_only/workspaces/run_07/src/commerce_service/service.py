from datetime import datetime, timezone
from fastapi import HTTPException
from .repository import Repository


EXPIRATION_SECONDS = 300


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int):
        existing = self.repo.get_sku(sku)
        if existing:
            raise HTTPException(status_code=400, detail="SKU already exists")
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int):
        sku_obj = self.repo.get_sku(sku)
        if not sku_obj:
            raise HTTPException(status_code=404, detail="SKU not found")
        return self.repo.update_sku_stock(sku, amount)

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str):
        existing_reservation = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing_reservation:
            return existing_reservation

        sku_obj = self.repo.get_sku(sku)
        if not sku_obj:
            raise HTTPException(status_code=404, detail="SKU not found")

        if sku_obj.stock < quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")

        self.repo.update_sku_stock(sku, -quantity)
        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        return reservation

    def confirm_reservation(self, reservation_id: int):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation.status != "PENDING":
            raise HTTPException(status_code=400, detail="Reservation is not in PENDING status")

        now = datetime.now(timezone.utc)
        created_at = reservation.created_at.replace(tzinfo=timezone.utc) if reservation.created_at.tzinfo is None else reservation.created_at
        elapsed = (now - created_at).total_seconds()

        if elapsed > EXPIRATION_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.update_sku_stock(reservation.sku, reservation.quantity)
            raise HTTPException(status_code=400, detail="Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(reservation_id, reservation.sku, reservation.quantity)
        return order

    def cancel_reservation(self, reservation_id: int):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation.status != "PENDING":
            raise HTTPException(status_code=400, detail="Reservation is not in PENDING status")

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.update_sku_stock(reservation.sku, reservation.quantity)
        return {"detail": "Reservation cancelled"}

    def get_orders(self, page: int = 1, size: int = 10):
        orders, total = self.repo.get_orders_paginated(page, size)
        return orders, total
