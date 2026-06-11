import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Tuple, List
import os


DB_PATH = os.environ.get("DATABASE_URL", ":memory:")


class Repository:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._persistent_conn = None
        if db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(db_path, check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_db()

    @contextmanager
    def _get_connection(self):
        if self._persistent_conn:
            conn = self._persistent_conn
            owns_conn = False
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            owns_conn = True
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if owns_conn:
                conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS skus (
                    sku TEXT PRIMARY KEY,
                    initial_stock INTEGER NOT NULL,
                    available_stock INTEGER NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reservation_id INTEGER NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (reservation_id) REFERENCES reservations(id)
                )
                """
            )

    def create_sku(self, sku: str, initial_stock: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO skus (sku, initial_stock, available_stock) VALUES (?, ?, ?)",
                (sku, initial_stock, initial_stock),
            )

    def get_sku(self, sku: str) -> Optional[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
                (amount, sku),
            )
            cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_available_stock(self, sku: str) -> Optional[int]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return row[0] if row else None

    def check_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, sku, quantity, status, created_at, idempotency_key FROM reservations WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str, created_at: str
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO reservations (sku, quantity, idempotency_key, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (sku, quantity, idempotency_key, "PENDING", created_at),
            )
            return cursor.lastrowid

    def deduct_stock(self, sku: str, quantity: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET available_stock = available_stock - ? WHERE sku = ?",
                (quantity, sku),
            )

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, sku, quantity, status, created_at, idempotency_key FROM reservations WHERE id = ?",
                (reservation_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id),
            )

    def create_order(self, reservation_id: int, created_at: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
                (reservation_id, created_at),
            )
            return cursor.lastrowid

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[List[dict], int]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            offset = (page - 1) * size
            cursor.execute(
                "SELECT id, reservation_id, created_at FROM orders ORDER BY id ASC LIMIT ? OFFSET ?",
                (size, offset),
            )
            orders = [dict(row) for row in cursor.fetchall()]
            cursor.execute("SELECT COUNT(*) FROM orders")
            total = cursor.fetchone()[0]
            return orders, total

    def clear_all(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM orders")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("DELETE FROM reservations")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("DELETE FROM skus")
            except sqlite3.OperationalError:
                pass
