import sqlite3
from contextlib import contextmanager
from typing import Optional, Tuple, List
from datetime import datetime
import os


DB_PATH = os.environ.get("DATABASE_PATH", "commerce.db")


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    sku TEXT PRIMARY KEY,
                    stock INTEGER NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    idempotency_key TEXT UNIQUE,
                    created_at TEXT NOT NULL,
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

    def create_sku(self, sku: str, initial_stock: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO skus (sku, stock) VALUES (?, ?)",
                (sku, initial_stock)
            )

    def get_sku_stock(self, sku: str) -> Optional[int]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return row[0] if row else None

    def adjust_stock(self, sku: str, amount: int) -> Optional[int]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET stock = stock + ? WHERE sku = ?",
                (amount, sku)
            )
            if cursor.rowcount == 0:
                return None
            cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return row[0] if row else None

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Tuple[int, str]:
        now = datetime.utcnow().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO reservations (sku, quantity, status, idempotency_key, created_at)
                   VALUES (?, ?, 'PENDING', ?, ?)""",
                (sku, quantity, idempotency_key, now)
            )
            reservation_id = cursor.lastrowid
            return reservation_id, now

    def get_reservation_by_idempotency_key(self, idempotency_key: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, sku, quantity, status, idempotency_key, created_at FROM reservations WHERE idempotency_key = ?",
                (idempotency_key,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "sku": row[1],
                    "quantity": row[2],
                    "status": row[3],
                    "idempotency_key": row[4],
                    "created_at": row[5],
                }
            return None

    def get_reservation(self, reservation_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, sku, quantity, status, idempotency_key, created_at FROM reservations WHERE id = ?",
                (reservation_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "sku": row[1],
                    "quantity": row[2],
                    "status": row[3],
                    "idempotency_key": row[4],
                    "created_at": row[5],
                }
            return None

    def update_reservation_status(self, reservation_id: int, status: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id)
            )
            return cursor.rowcount > 0

    def create_order(self, reservation_id: int) -> int:
        now = datetime.utcnow().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
                (reservation_id, now)
            )
            return cursor.lastrowid

    def get_order(self, order_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, reservation_id, created_at FROM orders WHERE id = ?",
                (order_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "reservation_id": row[1],
                    "created_at": row[2],
                }
            return None

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[List, int]:
        offset = (page - 1) * size
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM orders"
            )
            total = cursor.fetchone()[0]
            cursor.execute(
                "SELECT id, reservation_id, created_at FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
                (size, offset)
            )
            rows = cursor.fetchall()
            orders = [
                {
                    "id": row[0],
                    "reservation_id": row[1],
                    "created_at": row[2],
                }
                for row in rows
            ]
            return orders, total

    def clear_all(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM orders")
            cursor.execute("DELETE FROM reservations")
            cursor.execute("DELETE FROM skus")
