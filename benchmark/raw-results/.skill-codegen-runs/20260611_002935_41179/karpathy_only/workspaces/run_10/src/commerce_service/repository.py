"""Repository layer for database operations."""

import sqlite3
from datetime import datetime
from pathlib import Path


class Database:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY,
                    sku TEXT UNIQUE NOT NULL,
                    available_stock INTEGER NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY,
                    sku_id INTEGER NOT NULL,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY,
                    reservation_id INTEGER NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (reservation_id) REFERENCES reservations(id)
                )
            """)
            conn.commit()

    def _get_connection(self):
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
                (sku, initial_stock),
            )
            conn.commit()
            row = cursor.execute(
                "SELECT sku, available_stock FROM skus WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            return dict(row)

    def get_sku(self, sku: str) -> dict | None:
        """Get a SKU by code."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, sku, available_stock FROM skus WHERE sku = ?", (sku,)
            ).fetchone()
            return dict(row) if row else None

    def adjust_stock(self, sku: str, amount: int) -> dict:
        """Adjust stock for a SKU."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
                (amount, sku),
            )
            conn.commit()
            row = cursor.execute(
                "SELECT sku, available_stock FROM skus WHERE sku = ?", (sku,)
            ).fetchone()
            return dict(row)

    def create_reservation(
        self, sku: str, sku_id: int, quantity: int, idempotency_key: str
    ) -> dict:
        """Create a new reservation."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """INSERT INTO reservations
                   (sku_id, sku, quantity, idempotency_key, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (sku_id, sku, quantity, idempotency_key, "PENDING", now),
            )
            conn.commit()
            row = cursor.execute(
                """SELECT id, sku, quantity, status, created_at
                   FROM reservations WHERE id = ?""",
                (cursor.lastrowid,),
            ).fetchone()
            return dict(row)

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        """Get a reservation by idempotency key."""
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT id, sku, quantity, status, created_at
                   FROM reservations WHERE idempotency_key = ?""",
                (idempotency_key,),
            ).fetchone()
            return dict(row) if row else None

    def get_reservation(self, reservation_id: int) -> dict | None:
        """Get a reservation by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT id, sku_id, sku, quantity, status, created_at
                   FROM reservations WHERE id = ?""",
                (reservation_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> dict:
        """Update reservation status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id),
            )
            conn.commit()
            row = cursor.execute(
                """SELECT id, sku, quantity, status, created_at
                   FROM reservations WHERE id = ?""",
                (reservation_id,),
            ).fetchone()
            return dict(row)

    def deduct_stock(self, sku: str, quantity: int):
        """Deduct stock for a SKU."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET available_stock = available_stock - ? WHERE sku = ?",
                (quantity, sku),
            )
            conn.commit()

    def restore_stock(self, sku: str, quantity: int):
        """Restore stock for a SKU."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
                (quantity, sku),
            )
            conn.commit()

    def create_order(self, reservation_id: int) -> dict:
        """Create an order from a reservation."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
                (reservation_id, now),
            )
            conn.commit()
            row = cursor.execute(
                "SELECT id, reservation_id, created_at FROM orders WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            return dict(row)

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        """Get paginated orders."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            offset = (page - 1) * size
            rows = cursor.execute(
                """SELECT id, reservation_id, created_at FROM orders
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (size, offset),
            ).fetchall()
            total = cursor.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            return [dict(row) for row in rows], total
