import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status

from .repository import Repository
from .models import ReservationStatus, OrderStatus


RESERVATION_EXPIRY_MINUTES = 30


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, name: str, initial_stock: int):
        existing = self.repo.get_sku(sku_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"SKU {sku_id} already exists",
            )
        return self.repo.create_sku(sku_id, name, initial_stock)

    def get_sku(self, sku_id: str):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )
        return sku

    def adjust_stock(self, sku_id: str, delta: int):
        sku = self.repo.adjust_sku_stock(sku_id, delta)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )
        return sku

    def create_reservation(self, sku_id: str, quantity: int, idempotency_key: str):
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == ReservationStatus.EXPIRED:
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="Reservation for this idempotency key has expired",
                )
            return existing

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )

        available = sku.current_stock - sku.reserved_stock
        if available < quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Insufficient stock. Available: {available}, Requested: {quantity}",
            )

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=RESERVATION_EXPIRY_MINUTES)

        reservation = self.repo.create_reservation(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

        self.repo.update_sku_reserved_stock(sku_id, quantity)

        return reservation

    def confirm_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation.status == ReservationStatus.EXPIRED:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Reservation has expired",
            )

        if reservation.status != ReservationStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Reservation is {reservation.status}, cannot confirm",
            )

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Reservation has expired",
            )

        order_id = str(uuid.uuid4())
        self.repo.create_order(order_id)
        self.repo.link_reservation_to_order(reservation_id, order_id)
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

        return self.repo.get_reservation(reservation_id)

    def cancel_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation.status == ReservationStatus.CANCELLED:
            return reservation

        if reservation.status not in (ReservationStatus.PENDING, ReservationStatus.CONFIRMED):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot cancel reservation with status {reservation.status}",
            )

        self.repo.update_sku_reserved_stock(reservation.sku_id, -reservation.quantity)
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

        return self.repo.get_reservation(reservation_id)

    def get_order(self, order_id: str):
        order = self.repo.get_order(order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found",
            )
        return order

    def list_orders(self, skip: int = 0, limit: int = 20):
        return self.repo.list_orders(skip, limit)
