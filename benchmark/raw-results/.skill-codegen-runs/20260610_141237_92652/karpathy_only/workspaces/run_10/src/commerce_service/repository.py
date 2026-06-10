import sqlite3
from contextlib import contextmanager
from typing import Optional, List, Dict, Any


class Repository:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self):
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
        with self._get_connection() as conn:
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
                    status TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(sku) REFERENCES skus(sku)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reservation_id INTEGER UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(reservation_id) REFERENCES reservations(id)
                )
            """)

    def create_sku(self, sku: str, initial_stock: int) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
                (sku, initial_stock)
            )
            sku_id = cursor.lastrowid
            return {
                "id": sku_id,
                "sku": sku,
                "available_stock": initial_stock
            }

    def get_sku_by_name(self, sku: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, sku, available_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def update_sku_stock(self, sku: str, new_stock: int) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET available_stock = ? WHERE sku = ?",
                (new_stock, sku)
            )
            cursor.execute("SELECT id, sku, available_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return dict(row)

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str,
        status: str,
        created_at: str
    ) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO reservations (sku, quantity, status, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (sku, quantity, status, idempotency_key, created_at)
            )
            reservation_id = cursor.lastrowid
            return {
                "id": reservation_id,
                "sku": sku,
                "quantity": quantity,
                "status": status,
                "created_at": created_at
            }

    def get_reservation(self, reservation_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, sku, quantity, status, created_at FROM reservations WHERE id = ?",
                (reservation_id,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, sku, quantity, status, created_at FROM reservations WHERE idempotency_key = ?",
                (idempotency_key,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def update_reservation_status(self, reservation_id: int, status: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id)
            )
            cursor.execute(
                "SELECT id, sku, quantity, status, created_at FROM reservations WHERE id = ?",
                (reservation_id,)
            )
            row = cursor.fetchone()
            return dict(row)

    def create_order(self, reservation_id: int, created_at: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
                (reservation_id, created_at)
            )
            order_id = cursor.lastrowid
            return {
                "id": order_id,
                "reservation_id": reservation_id,
                "created_at": created_at
            }

    def get_orders(self, offset: int, limit: int) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, reservation_id, created_at FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
