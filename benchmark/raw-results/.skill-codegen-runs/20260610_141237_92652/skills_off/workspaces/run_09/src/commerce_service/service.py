from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List
from commerce_service.repository import (
    SKURepository, ReservationRepository, OrderRepository
)
from commerce_service.models import ReservationResponse, OrderResponse, PaginatedOrders


class CommerceService:

    def create_sku(self, sku: str, initial_stock: int) -> Dict[str, Any]:
        sku_id = SKURepository.create_sku(sku, initial_stock)
        sku_data = SKURepository.get_by_id(sku_id)
        return {
            "sku": sku_data["sku"],
            "available_stock": sku_data["available_stock"],
            "total_stock": sku_data["total_stock"]
        }

    def adjust_stock(self, sku: str, amount: int) -> Dict[str, Any]:
        result = SKURepository.adjust_stock(sku, amount)
        if result is None:
            return None
        return {
            "sku": result["sku"],
            "available_stock": result["available_stock"],
            "total_stock": result["total_stock"]
        }

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> Tuple[Optional[ReservationResponse], Optional[str]]:
        existing = ReservationRepository.get_by_idempotency_key(idempotency_key)
        if existing:
            return ReservationResponse(**existing), None

        sku_data = SKURepository.get_by_sku(sku)
        if sku_data is None:
            return None, "SKU not found"

        if sku_data["available_stock"] < quantity:
            return None, "Insufficient stock"

        SKURepository.adjust_stock(sku, -quantity)
        reservation = ReservationRepository.create_reservation(sku_data["id"], quantity, idempotency_key)
        return ReservationResponse(**reservation), None

    def confirm_reservation(self, reservation_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        reservation = ReservationRepository.get_by_id(reservation_id)
        if reservation is None:
            return None, "Reservation not found"

        if reservation["status"] != "PENDING":
            return None, f"Reservation is not PENDING (current status: {reservation['status']})"

        created_at = datetime.fromisoformat(reservation["created_at"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        elapsed = (now - created_at).total_seconds()

        if elapsed > 300:
            ReservationRepository.update_status(reservation_id, "EXPIRED")
            quantity = ReservationRepository.get_quantity_by_id(reservation_id)
            sku_id = ReservationRepository.get_sku_id_by_id(reservation_id)
            sku_data = SKURepository.get_by_id(sku_id)
            SKURepository.adjust_stock(sku_data["sku"], quantity)
            return None, "Reservation expired"

        ReservationRepository.update_status(reservation_id, "CONFIRMED")
        order = OrderRepository.create_order(reservation_id)
        return order, None

    def cancel_reservation(self, reservation_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        reservation = ReservationRepository.get_by_id(reservation_id)
        if reservation is None:
            return None, "Reservation not found"

        if reservation["status"] != "PENDING":
            return None, f"Reservation is not PENDING (current status: {reservation['status']})"

        quantity = ReservationRepository.get_quantity_by_id(reservation_id)
        sku_id = ReservationRepository.get_sku_id_by_id(reservation_id)
        sku_data = SKURepository.get_by_id(sku_id)
        SKURepository.adjust_stock(sku_data["sku"], quantity)

        updated = ReservationRepository.update_status(reservation_id, "CANCELLED")
        return updated, None

    def get_orders_paginated(self, page: int, size: int) -> PaginatedOrders:
        orders, total = OrderRepository.get_orders_paginated(page, size)
        items = [OrderResponse(**order) for order in orders]
        return PaginatedOrders(page=page, size=size, total=total, items=items)
