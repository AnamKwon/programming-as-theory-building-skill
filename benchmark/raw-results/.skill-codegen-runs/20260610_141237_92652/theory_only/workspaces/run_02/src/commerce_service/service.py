from datetime import datetime, timedelta
from .repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.repository.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        result = self.repository.adjust_stock(sku, amount)
        if result is None:
            raise ValueError(f"SKU not found: {sku}")
        return result

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        existing = self.repository.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku_data = self.repository.get_sku_by_name(sku)
        if not sku_data:
            raise ValueError(f"SKU not found: {sku}")

        if sku_data['available_stock'] < quantity:
            raise ValueError("Insufficient stock")

        self.repository.adjust_stock(sku, -quantity)

        return self.repository.create_reservation(sku_data['id'], sku, quantity, idempotency_key)

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repository.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation['status'] != 'PENDING':
            raise ValueError(f"Cannot confirm reservation with status: {reservation['status']}")

        created_at = datetime.fromisoformat(reservation['created_at'])
        if datetime.utcnow() - created_at > timedelta(seconds=300):
            self.repository.update_reservation_status(reservation_id, 'EXPIRED')
            self.repository.adjust_stock(reservation['sku'], reservation['quantity'])
            raise ValueError("Reservation expired")

        self.repository.update_reservation_status(reservation_id, 'CONFIRMED')
        return self.repository.create_order(reservation_id)

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repository.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation['status'] != 'PENDING':
            raise ValueError(f"Cannot cancel reservation with status: {reservation['status']}")

        self.repository.update_reservation_status(reservation_id, 'CANCELLED')
        self.repository.adjust_stock(reservation['sku'], reservation['quantity'])

        return {'status': 'CANCELLED'}

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.repository.get_orders(page, size)
        return {
            'orders': orders,
            'total': total,
            'page': page,
            'size': size
        }
