from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .repository import Repository
from .models import ReservationStatus, OrderStatus


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class IdempotencyConflictError(Exception):
    pass


class CommerceService:
    RESERVATION_EXPIRY_MINUTES = 15

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, code: str, name: str):
        session = self.repo.get_session()
        try:
            sku = self.repo.create_sku(session, code, name)
            return {
                "id": sku.id,
                "code": sku.code,
                "name": sku.name,
            }
        finally:
            session.close()

    def adjust_stock(self, sku_id: int, quantity_delta: int):
        session = self.repo.get_session()
        try:
            sku = self.repo.get_sku_by_id(session, sku_id)
            if not sku:
                raise ValueError(f"SKU {sku_id} not found")

            stock = self.repo.adjust_stock(session, sku_id, quantity_delta)
            return {
                "sku_id": stock.sku_id,
                "quantity_available": stock.quantity_available,
            }
        finally:
            session.close()

    def create_reservation(self, sku_id: int, quantity: int, idempotency_key: str):
        session = self.repo.get_session()
        try:
            existing_reservation = self.repo.get_reservation_by_idempotency_key(session, idempotency_key)
            if existing_reservation:
                order = self.repo.get_order_by_id(session, existing_reservation.order_id)
                return self._format_order_response(order)

            sku = self.repo.get_sku_by_id(session, sku_id)
            if not sku:
                raise ValueError(f"SKU {sku_id} not found")

            stock = self.repo.get_stock(session, sku_id)
            if not stock or stock.quantity_available < quantity:
                raise InsufficientStockError(f"Insufficient stock for SKU {sku_id}")

            stock.quantity_available -= quantity
            session.commit()

            expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.RESERVATION_EXPIRY_MINUTES)
            reservation, order = self.repo.create_reservation(
                session,
                sku_id=sku_id,
                quantity=quantity,
                idempotency_key=idempotency_key,
                expires_at=expires_at,
            )

            return self._format_order_response(order)
        except IntegrityError:
            session.rollback()
            existing_reservation = self.repo.get_reservation_by_idempotency_key(session, idempotency_key)
            if existing_reservation:
                order = self.repo.get_order_by_id(session, existing_reservation.order_id)
                return self._format_order_response(order)
            raise
        finally:
            session.close()

    def confirm_reservation(self, reservation_id: int):
        session = self.repo.get_session()
        try:
            reservation = self.repo.get_reservation_by_id(session, reservation_id)
            if not reservation:
                raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

            if reservation.status == ReservationStatus.EXPIRED:
                raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

            if reservation.status != ReservationStatus.PENDING:
                raise InvalidStateTransitionError(
                    f"Cannot confirm reservation with status {reservation.status}"
                )

            if reservation.expires_at:
                expires_at = reservation.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > expires_at:
                    self.repo.update_reservation_status(session, reservation_id, ReservationStatus.EXPIRED)
                    raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

            self.repo.update_reservation_status(session, reservation_id, ReservationStatus.CONFIRMED)

            order = self.repo.get_order_by_id(session, reservation.order_id)
            all_confirmed = all(r.status == ReservationStatus.CONFIRMED for r in order.reservations)
            if all_confirmed:
                self.repo.update_order_status(session, order.id, OrderStatus.CONFIRMED)

            order = self.repo.get_order_by_id(session, reservation.order_id)
            return self._format_order_response(order)
        finally:
            session.close()

    def cancel_reservation(self, reservation_id: int):
        session = self.repo.get_session()
        try:
            reservation = self.repo.get_reservation_by_id(session, reservation_id)
            if not reservation:
                raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

            if reservation.status in [ReservationStatus.CANCELLED, ReservationStatus.EXPIRED]:
                raise InvalidStateTransitionError(
                    f"Cannot cancel reservation with status {reservation.status}"
                )

            stock = self.repo.get_stock(session, reservation.sku_id)
            if stock:
                stock.quantity_available += reservation.quantity
                session.commit()

            self.repo.update_reservation_status(session, reservation_id, ReservationStatus.CANCELLED)

            order = self.repo.get_order_by_id(session, reservation.order_id)
            all_inactive = all(
                r.status in [ReservationStatus.CANCELLED, ReservationStatus.EXPIRED]
                for r in order.reservations
            )
            if all_inactive:
                self.repo.update_order_status(session, order.id, OrderStatus.CANCELLED)

            order = self.repo.get_order_by_id(session, reservation.order_id)
            return self._format_order_response(order)
        finally:
            session.close()

    def get_orders(self, page: int = 1, page_size: int = 10):
        session = self.repo.get_session()
        try:
            orders, total = self.repo.list_orders(session, page=page, page_size=page_size)
            return {
                "orders": [self._format_order_response(order) for order in orders],
                "total": total,
                "page": page,
                "page_size": page_size,
            }
        finally:
            session.close()

    def get_order(self, order_id: int):
        session = self.repo.get_session()
        try:
            order = self.repo.get_order_by_id(session, order_id)
            if not order:
                raise ValueError(f"Order {order_id} not found")
            return self._format_order_response(order)
        finally:
            session.close()

    def cleanup_expired_reservations(self):
        session = self.repo.get_session()
        try:
            now = datetime.now(timezone.utc)
            pending_reservations = self.repo.get_pending_reservations(session)

            for reservation in pending_reservations:
                if reservation.expires_at:
                    expires_at = reservation.expires_at
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    if now > expires_at:
                        self.repo.update_reservation_status(session, reservation.id, ReservationStatus.EXPIRED)

                        stock = self.repo.get_stock(session, reservation.sku_id)
                        if stock:
                            stock.quantity_available += reservation.quantity
                            session.commit()

                        order = self.repo.get_order_by_id(session, reservation.order_id)
                        all_inactive = all(
                            r.status in [ReservationStatus.CANCELLED, ReservationStatus.EXPIRED]
                            for r in order.reservations
                        )
                        if all_inactive:
                            self.repo.update_order_status(session, order.id, OrderStatus.CANCELLED)
        finally:
            session.close()

    def _format_order_response(self, order):
        return {
            "id": order.id,
            "status": order.status,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
            "reservations": [
                {
                    "id": res.id,
                    "order_id": res.order_id,
                    "sku_id": res.sku_id,
                    "quantity": res.quantity,
                    "status": res.status,
                    "idempotency_key": res.idempotency_key,
                    "created_at": res.created_at.isoformat(),
                    "expires_at": res.expires_at.isoformat() if res.expires_at else None,
                }
                for res in order.reservations
            ],
        }
