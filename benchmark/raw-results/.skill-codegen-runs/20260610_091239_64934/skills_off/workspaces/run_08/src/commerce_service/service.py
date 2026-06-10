from commerce_service.repository import Repository


class CommerceService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku_id: str, name: str, initial_stock: int) -> dict:
        try:
            return self.repo.create_sku(sku_id, name, initial_stock)
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                raise ValueError(f"SKU {sku_id} already exists")
            raise

    def adjust_stock(self, sku_id: str, delta: int) -> dict:
        return self.repo.adjust_stock(sku_id, delta)

    def reserve_stock(self, sku_id: str, quantity: int, idempotency_key: str) -> dict:
        return self.repo.create_reservation(sku_id, quantity, idempotency_key)

    def confirm_reservation(self, reservation_id: str) -> dict:
        return self.repo.confirm_reservation(reservation_id)

    def cancel_reservation(self, reservation_id: str) -> dict:
        return self.repo.cancel_reservation(reservation_id)

    def list_orders(self, limit: int = 10, offset: int = 0) -> dict:
        return self.repo.list_orders(limit, offset)
