import uuid
from datetime import datetime, timedelta

from .models import ReservationStatus
from .repository import Repository


class ReservationError(Exception):
    pass


class InsufficientStockError(ReservationError):
    pass


class ReservationNotFoundError(ReservationError):
    pass


class InvalidStateTransitionError(ReservationError):
    pass


class ReservationExpiredError(ReservationError):
    pass


class DuplicateReservationError(ReservationError):
    pass


class CommerceService:
    RESERVATION_TTL_MINUTES = 10

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, stock: int) -> dict:
        """Create a new SKU with initial stock level."""
        existing = self.repo.get_sku(sku)
        if existing:
            raise ReservationError(f"SKU {sku} already exists")

        result = self.repo.create_sku(sku, stock)
        return self._format_sku(result)

    def get_sku(self, sku: str) -> dict:
        """Get SKU with current stock and availability."""
        result = self.repo.get_sku(sku)
        if not result:
            raise ReservationError(f"SKU {sku} not found")

        return self._format_sku(result)

    def adjust_stock(self, sku: str, adjustment: int) -> dict:
        """Adjust stock level for a SKU."""
        existing = self.repo.get_sku(sku)
        if not existing:
            raise ReservationError(f"SKU {sku} not found")

        new_stock = existing["stock"] + adjustment
        if new_stock < 0:
            raise ReservationError(f"Cannot adjust stock below 0 (current: {existing['stock']}, adjustment: {adjustment})")

        result = self.repo.adjust_stock(sku, adjustment)
        return self._format_sku(result)

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str,
        customer_id: str,
    ) -> dict:
        """Create a reservation, checking for duplicates and stock availability."""
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing["status"] == ReservationStatus.PENDING.value:
                return self._format_reservation(existing)
            elif existing["status"] == ReservationStatus.CONFIRMED.value:
                raise DuplicateReservationError(
                    f"Idempotency key {idempotency_key} already confirmed as order"
                )
            else:
                raise DuplicateReservationError(
                    f"Idempotency key {idempotency_key} already used"
                )

        sku_data = self.repo.get_sku(sku)
        if not sku_data:
            raise ReservationError(f"SKU {sku} not found")

        available = sku_data["stock"] - sku_data["reserved"]
        if quantity > available:
            raise InsufficientStockError(
                f"Insufficient stock for {sku}: requested {quantity}, available {available}"
            )

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        result = self.repo.create_reservation(
            reservation_id=reservation_id,
            sku=sku,
            quantity=quantity,
            customer_id=customer_id,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )

        return self._format_reservation(result)

    def confirm_reservation(
        self,
        reservation_id: str,
        idempotency_key: str,
    ) -> dict:
        """Confirm a pending reservation, converting it to an order."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation["idempotency_key"] != idempotency_key:
            raise ReservationError("Idempotency key mismatch")

        if reservation["status"] == ReservationStatus.CONFIRMED.value:
            order_id = self._get_order_id_for_reservation(reservation_id)
            return {
                "id": reservation["id"],
                "sku": reservation["sku"],
                "quantity": reservation["quantity"],
                "status": ReservationStatus.CONFIRMED,
                "customer_id": reservation["customer_id"],
                "order_id": order_id,
                "created_at": datetime.fromisoformat(reservation["created_at"]),
                "confirmed_at": None,
            }

        if reservation["status"] != ReservationStatus.PENDING.value:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in {reservation['status']} state"
            )

        expires_at = datetime.fromisoformat(reservation["expires_at"])
        if datetime.utcnow() > expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError(
                f"Reservation {reservation_id} expired at {expires_at.isoformat()}"
            )

        order_id = str(uuid.uuid4())
        self.repo.create_order(
            order_id=order_id,
            reservation_id=reservation_id,
            sku=reservation["sku"],
            quantity=reservation["quantity"],
            customer_id=reservation["customer_id"],
        )

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

        result = self.repo.get_reservation(reservation_id)
        return {
            "id": result["id"],
            "sku": result["sku"],
            "quantity": result["quantity"],
            "status": ReservationStatus.CONFIRMED,
            "customer_id": result["customer_id"],
            "order_id": order_id,
            "created_at": datetime.fromisoformat(result["created_at"]),
            "confirmed_at": datetime.utcnow(),
        }

    def cancel_reservation(self, reservation_id: str) -> dict:
        """Cancel a pending reservation, releasing reserved stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation["status"] != ReservationStatus.PENDING.value:
            raise InvalidStateTransitionError(
                f"Cannot cancel reservation in {reservation['status']} state"
            )

        self.repo.release_reservation_stock(reservation_id)
        result = self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
        return self._format_reservation(result)

    def list_orders(self, page: int = 1, page_size: int = 10) -> dict:
        """List orders with pagination."""
        orders, total = self.repo.list_orders(page, page_size)

        total_pages = (total + page_size - 1) // page_size

        return {
            "items": [self._format_order(order) for order in orders],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def get_order(self, order_id: str) -> dict:
        """Get a specific order."""
        order = self.repo.get_order(order_id)
        if not order:
            raise ReservationError(f"Order {order_id} not found")

        return self._format_order(order)

    def _get_order_id_for_reservation(self, reservation_id: str) -> str:
        """Get the order ID for a confirmed reservation."""
        conn = self.repo._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM orders WHERE reservation_id = ?",
            (reservation_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return row["id"]
        return None

    @staticmethod
    def _format_sku(sku_data: dict) -> dict:
        return {
            "sku": sku_data["sku"],
            "stock": sku_data["stock"],
            "reserved": sku_data["reserved"],
            "available": sku_data["stock"] - sku_data["reserved"],
            "created_at": datetime.fromisoformat(sku_data["created_at"]),
        }

    @staticmethod
    def _format_reservation(reservation_data: dict) -> dict:
        return {
            "id": reservation_data["id"],
            "sku": reservation_data["sku"],
            "quantity": reservation_data["quantity"],
            "status": ReservationStatus(reservation_data["status"]),
            "customer_id": reservation_data["customer_id"],
            "idempotency_key": reservation_data["idempotency_key"],
            "created_at": datetime.fromisoformat(reservation_data["created_at"]),
            "expires_at": datetime.fromisoformat(reservation_data["expires_at"]),
        }

    @staticmethod
    def _format_order(order_data: dict) -> dict:
        return {
            "id": order_data["id"],
            "sku": order_data["sku"],
            "quantity": order_data["quantity"],
            "customer_id": order_data["customer_id"],
            "reservation_id": order_data["reservation_id"],
            "created_at": datetime.fromisoformat(order_data["created_at"]),
            "confirmed_at": datetime.fromisoformat(order_data["confirmed_at"]),
        }
