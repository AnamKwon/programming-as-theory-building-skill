"""Data access layer for database operations."""

import sqlite3
from datetime import datetime
from typing import Optional, Tuple, List


class Database:
    """SQLite database manager."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._connection = None

    def get_connection(self) -> sqlite3.Connection:
        """Get database connection (shared singleton)."""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def init_schema(self) -> None:
        """Initialize database schema."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                available_stock INTEGER NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus (id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations (id)
            )
            """
        )

        conn.commit()


class SKURepository:
    """Repository for SKU operations."""

    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> Tuple[int, str, int]:
        """Create a new SKU and return (id, sku, available_stock)."""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
            (sku, initial_stock),
        )
        conn.commit()

        sku_id = cursor.lastrowid
        return sku_id, sku, initial_stock

    def get_sku_by_name(self, sku: str) -> Optional[Tuple[int, str, int]]:
        """Get SKU by name. Returns (id, sku, available_stock) or None."""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, sku, available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()

        if row:
            return tuple(row)
        return None

    def adjust_stock(self, sku_id: int, amount: int) -> Optional[int]:
        """Adjust stock by amount. Returns new stock level or None if SKU not found."""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE id = ?",
            (amount, sku_id),
        )
        conn.commit()

        if cursor.rowcount == 0:
            return None

        cursor.execute("SELECT available_stock FROM skus WHERE id = ?", (sku_id,))
        row = cursor.fetchone()
        return row[0] if row else None


class ReservationRepository:
    """Repository for reservation operations."""

    def __init__(self, db: Database):
        self.db = db

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str
    ) -> Tuple[int, int, int, str, datetime, str]:
        """
        Create a reservation. Returns (id, sku_id, quantity, status, created_at, idempotency_key).
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        now = datetime.utcnow()
        status = "PENDING"

        cursor.execute(
            """
            INSERT INTO reservations (sku_id, quantity, status, created_at, idempotency_key)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sku_id, quantity, status, now.isoformat(), idempotency_key),
        )
        conn.commit()

        res_id = cursor.lastrowid
        return res_id, sku_id, quantity, status, now, idempotency_key

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[Tuple[int, int, int, str, datetime, str]]:
        """
        Get reservation by idempotency key.
        Returns (id, sku_id, quantity, status, created_at, idempotency_key) or None.
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, sku_id, quantity, status, created_at, idempotency_key
            FROM reservations WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        )
        row = cursor.fetchone()

        if row:
            res_id, sku_id, quantity, status_val, created_at_str, idem_key = tuple(row)
            created_at = datetime.fromisoformat(created_at_str)
            return res_id, sku_id, quantity, status_val, created_at, idem_key
        return None

    def get_reservation_by_id(
        self, res_id: int
    ) -> Optional[Tuple[int, int, int, str, datetime, str]]:
        """
        Get reservation by ID.
        Returns (id, sku_id, quantity, status, created_at, idempotency_key) or None.
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, sku_id, quantity, status, created_at, idempotency_key
            FROM reservations WHERE id = ?
            """,
            (res_id,),
        )
        row = cursor.fetchone()

        if row:
            res_id, sku_id, quantity, status_val, created_at_str, idem_key = tuple(row)
            created_at = datetime.fromisoformat(created_at_str)
            return res_id, sku_id, quantity, status_val, created_at, idem_key
        return None

    def update_reservation_status(self, res_id: int, status: str) -> bool:
        """Update reservation status. Returns True if successful."""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, res_id),
        )
        conn.commit()

        return cursor.rowcount > 0


class OrderRepository:
    """Repository for order operations."""

    def __init__(self, db: Database):
        self.db = db

    def create_order(self, reservation_id: int) -> Tuple[int, int, datetime]:
        """Create an order. Returns (id, reservation_id, created_at)."""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        now = datetime.utcnow()

        cursor.execute(
            "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
            (reservation_id, now.isoformat()),
        )
        conn.commit()

        order_id = cursor.lastrowid
        return order_id, reservation_id, now

    def get_orders_paginated(
        self, page: int = 1, size: int = 10
    ) -> Tuple[List[Tuple[int, int, datetime]], int]:
        """
        Get paginated orders. Returns (orders, total_count).
        Each order is (id, reservation_id, created_at).
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM orders")
        total = cursor.fetchone()[0]

        offset = (page - 1) * size
        cursor.execute(
            """
            SELECT id, reservation_id, created_at FROM orders
            ORDER BY created_at DESC LIMIT ? OFFSET ?
            """,
            (size, offset),
        )
        rows = cursor.fetchall()

        orders = []
        for row in rows:
            order_id, res_id, created_at_str = tuple(row)
            created_at = datetime.fromisoformat(created_at_str)
            orders.append((order_id, res_id, created_at))

        return orders, total
