import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator, Optional


class Database:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self.init_schema()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
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

    def init_schema(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    stock INTEGER NOT NULL DEFAULT 0,
                    reserved INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    idempotency_key TEXT UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (sku_id) REFERENCES skus (id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL DEFAULT 'processing',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def create_sku(self, sku: str, name: str, initial_stock: int) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO skus (sku, name, stock) VALUES (?, ?, ?)",
                (sku, name, initial_stock),
            )
            return cursor.lastrowid

    def get_sku(self, sku_id: int) -> Optional[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM skus WHERE id = ?", (sku_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_sku_by_sku(self, sku: str) -> Optional[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def adjust_stock(self, sku_id: int, adjustment: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET stock = stock + ? WHERE id = ?",
                (adjustment, sku_id),
            )
            return cursor.rowcount > 0

    def create_reservation(
        self,
        order_id: str,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO reservations
                (order_id, sku_id, quantity, idempotency_key, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (order_id, sku_id, quantity, idempotency_key, expires_at.isoformat()),
            )
            return cursor.lastrowid

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res_dict = dict(row)
            res_dict["expires_at"] = datetime.fromisoformat(res_dict["expires_at"])
            res_dict["created_at"] = datetime.fromisoformat(res_dict["created_at"])
            return res_dict

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM reservations WHERE idempotency_key = ?", (key,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            res_dict = dict(row)
            res_dict["expires_at"] = datetime.fromisoformat(res_dict["expires_at"])
            res_dict["created_at"] = datetime.fromisoformat(res_dict["created_at"])
            return res_dict

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id),
            )
            return cursor.rowcount > 0

    def reserve_stock(self, sku_id: int, quantity: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET reserved = reserved + ? WHERE id = ?",
                (quantity, sku_id),
            )
            return cursor.rowcount > 0

    def release_stock(self, sku_id: int, quantity: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET reserved = reserved - ? WHERE id = ?",
                (quantity, sku_id),
            )
            return cursor.rowcount > 0

    def create_or_get_order(self, order_id: str) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM orders WHERE order_id = ?", (order_id,))
            row = cursor.fetchone()
            if row:
                return row["id"]

            cursor.execute(
                "INSERT INTO orders (order_id, status) VALUES (?, ?)",
                (order_id, "processing"),
            )
            return cursor.lastrowid

    def get_order(self, order_id: int) -> Optional[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res_dict = dict(row)
            res_dict["created_at"] = datetime.fromisoformat(res_dict["created_at"])
            return res_dict

    def list_orders(self, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) as count FROM orders")
            total = cursor.fetchone()["count"]

            cursor.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = cursor.fetchall()
            orders = []
            for row in rows:
                order_dict = dict(row)
                order_dict["created_at"] = datetime.fromisoformat(
                    order_dict["created_at"]
                )
                orders.append(order_dict)
            return orders, total

    def cleanup_expired_reservations(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """
                UPDATE reservations
                SET status = 'cancelled'
                WHERE status = 'pending' AND expires_at < ?
                """,
                (now,),
            )
