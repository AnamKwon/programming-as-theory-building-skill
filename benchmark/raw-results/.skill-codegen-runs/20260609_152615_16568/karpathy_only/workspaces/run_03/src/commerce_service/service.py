from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .models import ReservationResponse, SKUResponse
from .repository import OrderRepository, ReservationRepository, SKURepository


class CommerceService:
    def __init__(self, session: Session):
        self.session = session
        self.sku_repo = SKURepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.order_repo = OrderRepository(session)

    def create_sku(self, code: str, name: str, initial_stock: int) -> SKUResponse:
        sku = self.sku_repo.create(code=code, name=name, initial_stock=initial_stock)
        self.session.commit()
        return SKUResponse.model_validate(sku)

    def get_sku(self, sku_id: int) -> SKUResponse | None:
        sku = self.sku_repo.get_by_id(sku_id)
        return SKUResponse.model_validate(sku) if sku else None

    def adjust_stock(self, sku_id: int, quantity_change: int) -> SKUResponse:
        sku = self.sku_repo.get_by_id(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        if sku.available_stock + quantity_change < 0:
            raise ValueError(f"Insufficient available stock for SKU {sku_id}")

        self.sku_repo.update_stock(sku_id, available_delta=quantity_change)
        self.session.commit()

        updated_sku = self.sku_repo.get_by_id(sku_id)
        return SKUResponse.model_validate(updated_sku)

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str, ttl_seconds: int
    ) -> ReservationResponse:
        existing = self.reservation_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status in ("pending", "confirmed"):
                return ReservationResponse.model_validate(existing)
            if existing.status == "cancelled":
                raise ValueError("Idempotency key was already used and reservation was cancelled")

        sku = self.sku_repo.get_by_id(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        self._cleanup_expired_reservations()

        if sku.available_stock < quantity:
            raise ValueError(f"Insufficient stock for SKU {sku_id}. Available: {sku.available_stock}, Requested: {quantity}")

        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        reservation = self.reservation_repo.create(
            sku_id=sku_id, quantity=quantity, idempotency_key=idempotency_key, expires_at=expires_at
        )

        self.sku_repo.update_stock(sku_id, available_delta=-quantity, reserved_delta=quantity)
        self.session.commit()

        return ReservationResponse.model_validate(reservation)

    def confirm_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "pending":
            raise ValueError(f"Cannot confirm reservation in status {reservation.status}")

        if datetime.utcnow() > reservation.expires_at:
            self.reservation_repo.update_status(reservation_id, "cancelled")
            sku = self.sku_repo.get_by_id(reservation.sku_id)
            if sku:
                self.sku_repo.update_stock(
                    reservation.sku_id, available_delta=reservation.quantity, reserved_delta=-reservation.quantity
                )
            self.session.commit()
            raise ValueError("Reservation has expired")

        self.reservation_repo.update_status(reservation_id, "confirmed")
        self.sku_repo.update_stock(
            reservation.sku_id, available_delta=0, reserved_delta=-reservation.quantity
        )
        self.order_repo.create(sku_id=reservation.sku_id, quantity=reservation.quantity)
        self.session.commit()

        updated_reservation = self.reservation_repo.get_by_id(reservation_id)
        return ReservationResponse.model_validate(updated_reservation)

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status == "confirmed":
            raise ValueError("Cannot cancel a confirmed reservation")

        if reservation.status == "cancelled":
            return ReservationResponse.model_validate(reservation)

        self.reservation_repo.update_status(reservation_id, "cancelled")
        self.sku_repo.update_stock(
            reservation.sku_id, available_delta=reservation.quantity, reserved_delta=-reservation.quantity
        )
        self.session.commit()

        updated_reservation = self.reservation_repo.get_by_id(reservation_id)
        return ReservationResponse.model_validate(updated_reservation)

    def _cleanup_expired_reservations(self) -> None:
        now = datetime.utcnow()
        expired = self.reservation_repo.get_expired(now)
        for reservation in expired:
            self.reservation_repo.update_status(reservation.id, "cancelled")
            sku = self.sku_repo.get_by_id(reservation.sku_id)
            if sku:
                self.sku_repo.update_stock(
                    reservation.sku_id,
                    available_delta=reservation.quantity,
                    reserved_delta=-reservation.quantity,
                )
