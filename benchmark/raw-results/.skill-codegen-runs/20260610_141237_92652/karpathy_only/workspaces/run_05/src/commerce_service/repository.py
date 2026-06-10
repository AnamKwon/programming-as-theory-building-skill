import sqlite3
import threading
from typing import Optional, List, Tuple

_local = threading.local()

def get_connection():
    if not hasattr(_local, 'conn'):
        from commerce_service import DB_PATH
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.row_factory = sqlite3.Row
    return _local.conn

class Repository:
    @staticmethod
    def create_sku(sku: str, initial_stock: int) -> None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO skus (sku, stock) VALUES (?, ?)",
            (sku, initial_stock)
        )
        conn.commit()

    @staticmethod
    def get_sku_stock(sku: str) -> Optional[int]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        return row[0] if row else None

    @staticmethod
    def adjust_stock(sku: str, amount: int) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE skus SET stock = stock + ? WHERE sku = ?",
            (amount, sku)
        )
        conn.commit()
        cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        return row[0] if row else 0

    @staticmethod
    def create_reservation(sku: str, quantity: int, idempotency_key: str, created_at: float) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO reservations (sku, quantity, status, created_at, idempotency_key) VALUES (?, ?, ?, ?, ?)",
            (sku, quantity, "PENDING", created_at, idempotency_key)
        )
        conn.commit()
        return cursor.lastrowid

    @staticmethod
    def get_reservation_by_idempotency_key(idempotency_key: str) -> Optional[dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, status, created_at FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row["id"],
                "sku": row["sku"],
                "quantity": row["quantity"],
                "status": row["status"],
                "created_at": row["created_at"]
            }
        return None

    @staticmethod
    def get_reservation(reservation_id: int) -> Optional[dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, status, created_at FROM reservations WHERE id = ?",
            (reservation_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row["id"],
                "sku": row["sku"],
                "quantity": row["quantity"],
                "status": row["status"],
                "created_at": row["created_at"]
            }
        return None

    @staticmethod
    def update_reservation_status(reservation_id: int, status: str) -> None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id)
        )
        conn.commit()

    @staticmethod
    def create_order(reservation_id: int, created_at: float) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
            (reservation_id, created_at)
        )
        conn.commit()
        return cursor.lastrowid

    @staticmethod
    def get_orders(offset: int, limit: int) -> Tuple[List[dict], int]:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT id, reservation_id, created_at FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        rows = cursor.fetchall()
        orders = [{"id": row["id"], "reservation_id": row["reservation_id"], "created_at": row["created_at"]} for row in rows]
        return orders, total
