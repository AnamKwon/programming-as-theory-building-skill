"""Database repository for persistence operations."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from .models import OrderStatus, ReservationStatus


class Repository:
    """Repository for all database operations."""

    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT UNIQUE NOT NULL,
                    stock_qty INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT NOT NULL,
                    qty INTEGER NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reservation_id INTEGER NOT NULL UNIQUE,
                    sku TEXT NOT NULL,
                    qty INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (reservation_id) REFERENCES reservations(id),
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                );

                CREATE INDEX IF NOT EXISTS idx_reservations_idempotency_key
                    ON reservations(idempotency_key);
                CREATE INDEX IF NOT EXISTS idx_reservations_status
                    ON reservations(status);
                CREATE INDEX IF NOT EXISTS idx_orders_created_at
                    ON orders(created_at DESC);
                """
            )
            conn.commit()

    def create_sku(self, sku: str, stock_qty: int) -> dict:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO skus (sku, stock_qty) VALUES (?, ?)",
                (sku, stock_qty),
            )
            conn.commit()
            sku_id = cursor.lastrowid
            return self.get_sku_by_id(sku_id)

    def get_sku_by_id(self, sku_id: int) -> dict:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, sku, stock_qty, created_at FROM skus WHERE id = ?",
                (sku_id,),
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def get_sku_by_code(self, sku: str) -> dict:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, sku, stock_qty, created_at FROM skus WHERE sku = ?",
                (sku,),
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def adjust_stock(self, sku: str, delta: int) -> dict:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE skus SET stock_qty = stock_qty + ? WHERE sku = ?",
                (delta, sku),
            )
            conn.commit()
            return self.get_sku_by_code(sku)

    def get_reservation_by_idempotency_key(self, key: str) -> dict:
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT id, sku, qty, status, created_at, expires_at
                   FROM reservations WHERE idempotency_key = ?""",
                (key,),
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def create_reservation(
        self, sku: str, qty: int, idempotency_key: str, expires_at: datetime
    ) -> dict:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO reservations (sku, qty, idempotency_key, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (sku, qty, idempotency_key, expires_at),
            )
            conn.commit()
            reservation_id = cursor.lastrowid
            return self.get_reservation_by_id(reservation_id)

    def get_reservation_by_id(self, reservation_id: int) -> dict:
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT id, sku, qty, status, created_at, expires_at
                   FROM reservations WHERE id = ?""",
                (reservation_id,),
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def update_reservation_status(self, reservation_id: int, status: str):
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id),
            )
            conn.commit()

    def create_order(self, reservation_id: int, sku: str, qty: int) -> dict:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO orders (reservation_id, sku, qty)
                   VALUES (?, ?, ?)""",
                (reservation_id, sku, qty),
            )
            conn.commit()
            order_id = cursor.lastrowid
            return self.get_order_by_id(order_id)

    def get_order_by_id(self, order_id: int) -> dict:
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT id, sku, qty, status, created_at FROM orders WHERE id = ?""",
                (order_id,),
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def get_orders(self, page: int, page_size: int) -> tuple[list[dict], int]:
        with self._get_connection() as conn:
            offset = (page - 1) * page_size
            rows = conn.execute(
                """SELECT id, sku, qty, status, created_at FROM orders
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (page_size, offset),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            return [dict(row) for row in rows], total

    def update_order_status(self, order_id: int, status: str):
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE orders SET status = ? WHERE order_id = ?",
                (status, order_id),
            )
            conn.commit()

    def get_expired_reservations(self) -> list[dict]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT id, sku, qty, status FROM reservations
                   WHERE status = ? AND expires_at < CURRENT_TIMESTAMP""",
                (ReservationStatus.PENDING.value,),
            ).fetchall()
            return [dict(row) for row in rows]

    def clear_db(self):
        """Drop all tables. Used for testing."""
        with self._get_connection() as conn:
            conn.executescript(
                """
                DROP TABLE IF EXISTS orders;
                DROP TABLE IF EXISTS reservations;
                DROP TABLE IF EXISTS skus;
                """
            )
            conn.commit()
        self._init_db()
