from datetime import datetime
from fastapi import HTTPException, status
from .repository import Repository
from .models import (
    CreateSKURequest,
    CreateReservationRequest,
    ReservationStatus,
    OrderStatus,
)


class Service:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, req: CreateSKURequest) -> dict:
        try:
            return self.repo.create_sku(req.sku_code, req.name, req.initial_stock)
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"SKU code '{req.sku_code}' already exists",
            )

    def adjust_stock(self, sku_id: int, quantity: int) -> dict:
        try:
            new_stock = self.repo.adjust_stock(sku_id, quantity)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )

        if new_stock < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        return self.repo.get_sku(sku_id)

    def create_order(self) -> dict:
        return self.repo.create_order()

    def get_order(self, order_id: int) -> dict:
        order = self.repo.get_order(order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found",
            )
        return order

    def create_reservation(self, order_id: int, req: CreateReservationRequest) -> dict:
        order = self.get_order(order_id)

        existing = self.repo.get_reservation_by_idempotency_key(req.idempotency_key)
        if existing:
            return existing

        sku = self.repo.get_sku(req.sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {req.sku_id} not found",
            )

        if sku["stock"] < req.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for SKU {req.sku_id}",
            )

        self.repo.adjust_stock(req.sku_id, -req.quantity)

        return self.repo.create_reservation(
            req.sku_id,
            order_id,
            req.quantity,
            req.idempotency_key,
        )

    def confirm_reservation(self, order_id: int, reservation_id: int) -> dict:
        order = self.get_order(order_id)
        reservation = self.repo.get_reservation(reservation_id)

        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation["order_id"] != order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation does not belong to this order",
            )

        expires_at = datetime.fromisoformat(reservation["expires_at"])
        if datetime.utcnow() > expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation has expired",
            )

        if reservation["status"] != ReservationStatus.RESERVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot confirm reservation with status '{reservation['status']}'",
            )

        return self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

    def cancel_reservation(self, order_id: int, reservation_id: int) -> dict:
        order = self.get_order(order_id)
        reservation = self.repo.get_reservation(reservation_id)

        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation["order_id"] != order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation does not belong to this order",
            )

        if reservation["status"] in (ReservationStatus.CANCELLED, ReservationStatus.EXPIRED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel reservation with status '{reservation['status']}'",
            )

        self.repo.adjust_stock(reservation["sku_id"], reservation["quantity"])
        return self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)


import sqlite3
