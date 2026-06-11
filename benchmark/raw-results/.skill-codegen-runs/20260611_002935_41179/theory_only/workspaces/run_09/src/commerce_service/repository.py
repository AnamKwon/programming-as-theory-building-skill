import sqlite3
from datetime import datetime, timezone
from typing import Optional, Tuple, List
import json
import os


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._shared_conn = None
        if db_path == ":memory:":
            # For in-memory databases, use a single shared connection
            self._shared_conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._shared_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._shared_conn:
            return self._shared_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _close_conn(self, conn: sqlite3.Connection):
        """Close connection only if it's not the shared connection."""
        if not self._shared_conn:
            conn.close()

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                stock INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT UNIQUE,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS idempotency_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idempotency_key TEXT UNIQUE NOT NULL,
                response TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
        """)

        conn.commit()
        self._close_conn(conn)

    def create_sku(self, sku: str, initial_stock: int) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "INSERT INTO skus (sku, stock, created_at) VALUES (?, ?, ?)",
            (sku, initial_stock, now)
        )
        conn.commit()
        sku_id = cursor.lastrowid
        self._close_conn(conn)
        return sku_id

    def get_sku_by_name(self, sku: str) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, sku, stock, created_at FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        self._close_conn(conn)
        return dict(row) if row else None

    def get_stock(self, sku: str) -> Optional[int]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        self._close_conn(conn)
        return row[0] if row else None

    def adjust_stock(self, sku: str, amount: int) -> Optional[int]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        if not row:
            self._close_conn(conn)
            return None
        new_stock = row[0] + amount
        cursor.execute("UPDATE skus SET stock = ? WHERE sku = ?", (new_stock, sku))
        conn.commit()
        self._close_conn(conn)
        return new_stock

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()

        sku_row = self.get_sku_by_name(sku)
        sku_id = sku_row['id']

        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """INSERT INTO reservations
               (sku_id, sku, quantity, status, idempotency_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sku_id, sku, quantity, "PENDING", idempotency_key, now)
        )
        conn.commit()
        reservation_id = cursor.lastrowid
        self._close_conn(conn)

        return {
            "id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "status": "PENDING",
            "created_at": now
        }

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, status, created_at FROM reservations WHERE id = ?",
            (reservation_id,)
        )
        row = cursor.fetchone()
        self._close_conn(conn)
        return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, status, created_at FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,)
        )
        row = cursor.fetchone()
        self._close_conn(conn)
        return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id)
        )
        conn.commit()
        affected = cursor.rowcount
        self._close_conn(conn)
        return affected > 0

    def create_order(self, reservation_id: int) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
            (reservation_id, now)
        )
        conn.commit()
        order_id = cursor.lastrowid
        self._close_conn(conn)
        return order_id

    def get_order(self, order_id: int) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, reservation_id, created_at FROM orders WHERE id = ?",
            (order_id,)
        )
        row = cursor.fetchone()
        self._close_conn(conn)
        return dict(row) if row else None

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> Tuple[List[dict], int]:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM orders")
        total = cursor.fetchone()[0]

        offset = (page - 1) * size
        cursor.execute(
            "SELECT id, reservation_id, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (size, offset)
        )
        rows = cursor.fetchall()
        self._close_conn(conn)

        return [dict(row) for row in rows], total

    def cache_idempotent_response(self, idempotency_key: str, response: dict) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        response_json = json.dumps(response, default=str)
        try:
            cursor.execute(
                "INSERT INTO idempotency_cache (idempotency_key, response, created_at) VALUES (?, ?, ?)",
                (idempotency_key, response_json, now)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        self._close_conn(conn)

    def get_cached_response(self, idempotency_key: str) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT response FROM idempotency_cache WHERE idempotency_key = ?",
            (idempotency_key,)
        )
        row = cursor.fetchone()
        self._close_conn(conn)
        if row:
            return json.loads(row[0])
        return None

    def clear_db(self):
        """Clear all tables. Used for testing."""
        if self.db_path == ":memory:":
            # For in-memory databases, drop all tables
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS idempotency_cache")
            cursor.execute("DROP TABLE IF EXISTS orders")
            cursor.execute("DROP TABLE IF EXISTS reservations")
            cursor.execute("DROP TABLE IF EXISTS skus")
            conn.commit()
            self._init_db()
        else:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
            self._init_db()
