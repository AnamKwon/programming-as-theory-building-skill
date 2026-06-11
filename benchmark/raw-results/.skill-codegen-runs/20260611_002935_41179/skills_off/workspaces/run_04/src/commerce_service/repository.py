import sqlite3
from datetime import datetime
from typing import Optional, List, Tuple
import os


DB_PATH = os.environ.get("DB_PATH", ":memory:")


class Repository:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                available_stock INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            )
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
            (sku, initial_stock)
        )
        conn.commit()
        sku_id = cursor.lastrowid
        conn.close()

        return {"id": sku_id, "sku": sku, "available_stock": initial_stock}

    def get_sku_by_name(self, sku: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, sku, available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
            (amount, sku)
        )
        conn.commit()

        cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        return {"sku": sku, "available_stock": row[0]}

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.utcnow().isoformat()
        cursor.execute(
            """INSERT INTO reservations (sku, quantity, status, created_at, idempotency_key)
               VALUES (?, ?, 'PENDING', ?, ?)""",
            (sku, quantity, now, idempotency_key)
        )
        conn.commit()
        reservation_id = cursor.lastrowid
        conn.close()

        return {
            "id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "status": "PENDING",
            "created_at": now,
            "idempotency_key": idempotency_key,
        }

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, sku, quantity, status, created_at, idempotency_key FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,)
        )
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    def get_reservation_by_id(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, sku, quantity, status, created_at, idempotency_key FROM reservations WHERE id = ?",
            (reservation_id,)
        )
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id)
        )
        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()

        return rows_affected > 0

    def create_order(self, reservation_id: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.utcnow().isoformat()
        cursor.execute(
            "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
            (reservation_id, now)
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()

        return {"id": order_id, "reservation_id": reservation_id, "created_at": now}

    def list_orders(self, page: int, size: int) -> Tuple[List[dict], int]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM orders")
        total = cursor.fetchone()[0]

        offset = (page - 1) * size
        cursor.execute(
            "SELECT id, reservation_id, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (size, offset)
        )
        rows = cursor.fetchall()
        conn.close()

        orders = [dict(row) for row in rows]
        return orders, total

    def deduct_stock(self, sku: str, quantity: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE skus SET available_stock = available_stock - ? WHERE sku = ?",
            (quantity, sku)
        )
        conn.commit()

        cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        return {"sku": sku, "available_stock": row[0]}

    def restore_stock(self, sku: str, quantity: int) -> Optional[dict]:
        return self.adjust_stock(sku, quantity)
