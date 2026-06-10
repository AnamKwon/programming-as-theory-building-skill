"""Business logic layer."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .models import OrderModel, OrderResponse, OrderStatus, ReservationModel, ReservationResponse, ReservationStatus, SKUResponse, StockResponse
from .repository import Repository


class CommerceService:
    """Handles business logic for reservations and orders."""

    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, name: str) -> SKUResponse:
        """Create a new SKU."""
        session = self.repo.get_session()
        try:
            # Check if SKU already exists
            existing = self.repo.get_sku(session, sku_id)
            if existing:
                raise ValueError(f"SKU {sku_id} already exists")

            sku = self.repo.create_sku(session, sku_id, name)
            return SKUResponse.model_validate(sku)
        finally:
            session.close()

    def adjust_stock(self, sku_id: str, delta: int) -> StockResponse:
        """Adjust stock for a SKU."""
        if delta == 0:
            raise ValueError("Stock delta cannot be zero")

        session = self.repo.get_session()
        try:
            # Ensure SKU exists
            sku = self.repo.get_sku(session, sku_id)
            if not sku:
                raise ValueError(f"SKU {sku_id} does not exist")

            stock = self.repo.update_stock(session, sku_id, delta)
            if stock.quantity < 0:
                stock.quantity = 0
                session.commit()

            return StockResponse.model_validate(stock)
        finally:
            session.close()

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str = None
    ) -> ReservationResponse:
        """Create a reservation with idempotency."""
        session = self.repo.get_session()
        try:
            # Check idempotency
            if idempotency_key:
                existing = self.repo.get_reservation_by_idempotency_key(session, idempotency_key)
                if existing:
                    return ReservationResponse.model_validate(existing)

            # Cleanup expired reservations first
            self.repo.cleanup_expired_reservations(session)

            # Check SKU exists
            sku = self.repo.get_sku(session, sku_id)
            if not sku:
                raise ValueError(f"SKU {sku_id} does not exist")

            # Check stock availability
            stock = self.repo.get_stock(session, sku_id)
            available = stock.quantity if stock else 0

            if available < quantity:
                raise ValueError(
                    f"Insufficient stock for {sku_id}: requested {quantity}, available {available}"
                )

            # Create reservation
            reservation_id = str(uuid.uuid4())
            expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

            reservation = self.repo.create_reservation(
                session,
                reservation_id,
                sku_id,
                quantity,
                expires_at,
                idempotency_key,
            )

            # Reserve stock (don't update stock yet, just hold reservation)
            return ReservationResponse.model_validate(reservation)
        finally:
            session.close()

    def confirm_reservation(self, reservation_id: str) -> OrderResponse:
        """Confirm a reservation and create an order."""
        session = self.repo.get_session()
        try:
            reservation = self.repo.get_reservation(session, reservation_id)
            if not reservation:
                raise ValueError(f"Reservation {reservation_id} not found")

            # Check if already has an order
            existing_order = self.repo.get_order_by_reservation_id(session, reservation_id)
            if existing_order:
                return OrderResponse.model_validate(existing_order)

            # Validate reservation state
            if reservation.status == ReservationStatus.EXPIRED:
                raise ValueError(f"Reservation {reservation_id} has expired")

            if reservation.status in (
                ReservationStatus.CONFIRMED,
                ReservationStatus.CANCELLED,
            ):
                raise ValueError(
                    f"Cannot confirm reservation in {reservation.status} state"
                )

            # Verify stock is still available
            stock = self.repo.get_stock(session, reservation.sku_id)
            available = stock.quantity if stock else 0

            if available < reservation.quantity:
                raise ValueError(
                    f"Stock no longer available for {reservation.sku_id}: "
                    f"requested {reservation.quantity}, available {available}"
                )

            # Reserve the stock
            self.repo.update_stock(session, reservation.sku_id, -reservation.quantity)

            # Update reservation status
            self.repo.update_reservation_status(
                session, reservation_id, ReservationStatus.CONFIRMED
            )

            # Create order
            order_id = str(uuid.uuid4())
            order = self.repo.create_order(
                session,
                order_id,
                reservation_id,
                reservation.sku_id,
                reservation.quantity,
            )

            return OrderResponse.model_validate(order)
        finally:
            session.close()

    def cancel_reservation(self, reservation_id: str) -> ReservationResponse:
        """Cancel a pending reservation."""
        session = self.repo.get_session()
        try:
            reservation = self.repo.get_reservation(session, reservation_id)
            if not reservation:
                raise ValueError(f"Reservation {reservation_id} not found")

            if reservation.status != ReservationStatus.PENDING:
                raise ValueError(
                    f"Can only cancel pending reservations, "
                    f"this one is {reservation.status}"
                )

            reservation = self.repo.update_reservation_status(
                session, reservation_id, ReservationStatus.CANCELLED
            )

            return ReservationResponse.model_validate(reservation)
        finally:
            session.close()

    def list_orders(self, page: int = 1, page_size: int = 10) -> dict:
        """List orders with pagination."""
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 10

        session = self.repo.get_session()
        try:
            orders, total = self.repo.list_orders(session, page, page_size)

            total_pages = (total + page_size - 1) // page_size

            return {
                "items": [OrderResponse.model_validate(order) for order in orders],
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            }
        finally:
            session.close()
