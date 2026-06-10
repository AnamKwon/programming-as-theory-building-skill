import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Generator

from .models import ReservationStatus, OrderStatus


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_conn(self) -> Generator[sqlite3.Connection, None, None]:
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
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    FOREIGN KEY (sku_id) REFERENCES skus(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    reservation_id INTEGER NOT NULL,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    FOREIGN KEY (order_id) REFERENCES orders(id),
                    FOREIGN KEY (reservation_id) REFERENCES reservations(id),
                    FOREIGN KEY (sku_id) REFERENCES skus(id)
                )
            """)

    def create_sku(self, name: str, quantity: int) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO skus (name, quantity) VALUES (?, ?)",
                (name, quantity)
            )
            return cursor.lastrowid

    def get_sku(self, sku_id: int) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id, name, quantity FROM skus WHERE id = ?",
                (sku_id,)
            ).fetchone()
            return dict(row) if row else None

    def adjust_stock(self, sku_id: int, adjustment: int) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "UPDATE skus SET quantity = quantity + ? WHERE id = ?",
                (adjustment, sku_id)
            )
            return cursor.rowcount > 0

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        expires_at: datetime,
        idempotency_key: str
    ) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reservations
                (sku_id, quantity, status, expires_at, idempotency_key)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sku_id, quantity, ReservationStatus.PENDING, expires_at, idempotency_key)
            )
            return cursor.lastrowid

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT id, sku_id, quantity, status, created_at, expires_at, idempotency_key
                FROM reservations WHERE id = ?
                """,
                (reservation_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT id, sku_id, quantity, status, created_at, expires_at, idempotency_key
                FROM reservations WHERE idempotency_key = ?
                """,
                (key,)
            ).fetchone()
            return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id)
            )
            return cursor.rowcount > 0

    def create_order(self) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO orders (status) VALUES (?)",
                (OrderStatus.DRAFT,)
            )
            return cursor.lastrowid

    def add_order_item(
        self,
        order_id: int,
        reservation_id: int,
        sku_id: int,
        quantity: int
    ) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO order_items (order_id, reservation_id, sku_id, quantity)
                VALUES (?, ?, ?, ?)
                """,
                (order_id, reservation_id, sku_id, quantity)
            )

    def update_order_status(self, order_id: int, status: str) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "UPDATE orders SET status = ? WHERE id = ?",
                (status, order_id)
            )
            return cursor.rowcount > 0

    def get_order(self, order_id: int) -> Optional[dict]:
        with self._get_conn() as conn:
            order_row = conn.execute(
                "SELECT id, status, created_at FROM orders WHERE id = ?",
                (order_id,)
            ).fetchone()
            if not order_row:
                return None

            items_rows = conn.execute(
                """
                SELECT reservation_id, sku_id, quantity FROM order_items WHERE order_id = ?
                """,
                (order_id,)
            ).fetchall()

            return {
                "id": order_row["id"],
                "status": order_row["status"],
                "created_at": order_row["created_at"],
                "items": [dict(row) for row in items_rows]
            }

    def list_orders(self, skip: int = 0, limit: int = 20) -> tuple[list[dict], int]:
        with self._get_conn() as conn:
            total_row = conn.execute("SELECT COUNT(*) as count FROM orders").fetchone()
            total = total_row["count"]

            orders_rows = conn.execute(
                "SELECT id, status, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, skip)
            ).fetchall()

            orders = []
            for order_row in orders_rows:
                items_rows = conn.execute(
                    """
                    SELECT reservation_id, sku_id, quantity FROM order_items WHERE order_id = ?
                    """,
                    (order_row["id"],)
                ).fetchall()
                orders.append({
                    "id": order_row["id"],
                    "status": order_row["status"],
                    "created_at": order_row["created_at"],
                    "items": [dict(row) for row in items_rows]
                })

            return orders, total
