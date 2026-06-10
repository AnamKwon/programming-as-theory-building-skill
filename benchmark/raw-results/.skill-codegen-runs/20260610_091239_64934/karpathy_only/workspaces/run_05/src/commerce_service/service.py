import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException, status

from .models import OrderStatus, ReservationStatus
from .repository import Repository


class CommerceService:
    def __init__(self, repo: Repository, reservation_ttl_minutes: int = 15):
        self.repo = repo
        self.reservation_ttl_minutes = reservation_ttl_minutes

    def create_sku(self, sku_id: str, name: str, total_stock: int) -> dict:
        existing = self.repo.get_sku(sku_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"SKU {sku_id} already exists",
            )

        sku = self.repo.create_sku(sku_id, name, total_stock)
        return {
            "sku_id": sku.sku_id,
            "name": sku.name,
            "total_stock": sku.total_stock,
            "reserved_stock": sku.reserved_stock,
            "available_stock": sku.total_stock - sku.reserved_stock,
        }

    def adjust_stock(self, sku_id: str, adjustment: int) -> dict:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )

        if sku.total_stock + adjustment < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Adjustment would result in negative stock",
            )

        sku = self.repo.update_sku_stock(sku_id, adjustment)
        return {
            "sku_id": sku.sku_id,
            "name": sku.name,
            "total_stock": sku.total_stock,
            "reserved_stock": sku.reserved_stock,
            "available_stock": sku.total_stock - sku.reserved_stock,
        }

    def create_reservation(self, sku_id: str, quantity: int, idempotency_key: str) -> dict:
        existing_reservation = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing_reservation:
            if existing_reservation.status in (ReservationStatus.CANCELLED, ReservationStatus.EXPIRED):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key was previously used for a cancelled/expired reservation",
                )
            return {
                "reservation_id": existing_reservation.reservation_id,
                "sku_id": existing_reservation.sku_id,
                "quantity": existing_reservation.quantity,
                "status": existing_reservation.status,
                "created_at": existing_reservation.created_at,
                "expires_at": existing_reservation.expires_at,
                "confirmed_at": existing_reservation.confirmed_at,
            }

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )

        available = sku.total_stock - sku.reserved_stock
        if available < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock: {available} available, {quantity} requested",
            )

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.reservation_ttl_minutes)

        reservation = self.repo.create_reservation(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )
        self.repo.update_sku_reserved_stock(sku_id, quantity)

        return {
            "reservation_id": reservation.reservation_id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
            "confirmed_at": reservation.confirmed_at,
        }

    def confirm_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation.status != ReservationStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Reservation is {reservation.status}, cannot confirm",
            )

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            self.repo.update_sku_reserved_stock(reservation.sku_id, -reservation.quantity)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reservation has expired",
            )

        confirmed_at = datetime.utcnow()
        reservation = self.repo.update_reservation_confirmed(
            reservation_id, ReservationStatus.CONFIRMED, confirmed_at
        )

        order_id = str(uuid.uuid4())
        self.repo.create_order(order_id, reservation_id, OrderStatus.CONFIRMED)

        return {
            "reservation_id": reservation.reservation_id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
            "confirmed_at": reservation.confirmed_at,
        }

    def cancel_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation.status == ReservationStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reservation is already cancelled",
            )

        if reservation.status == ReservationStatus.CONFIRMED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot cancel a confirmed reservation",
            )

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
        self.repo.update_sku_reserved_stock(reservation.sku_id, -reservation.quantity)

        reservation = self.repo.get_reservation(reservation_id)
        return {
            "reservation_id": reservation.reservation_id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
            "confirmed_at": reservation.confirmed_at,
        }

    def get_order(self, order_id: str) -> dict:
        order = self.repo.get_order(order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found",
            )
        return {
            "order_id": order.order_id,
            "reservation_id": order.reservation_id,
            "status": order.status,
            "created_at": order.created_at,
        }

    def list_orders(self, limit: int = 10, offset: int = 0) -> dict:
        orders, total = self.repo.list_orders(limit, offset)
        return {
            "orders": [
                {
                    "order_id": order.order_id,
                    "reservation_id": order.reservation_id,
                    "status": order.status,
                    "created_at": order.created_at,
                }
                for order in orders
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
