"""Database repository layer."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATABASE_PATH = Path(__file__).parent.parent.parent / "inventory.db"


class Repository:
    """Handles all database operations."""

    def __init__(self, db_path: str = str(DATABASE_PATH)):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize database tables."""
        conn = self._get_connection()
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
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY,
                reservation_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id),
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> int:
        """Create a new SKU with initial stock."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
            (sku, initial_stock),
        )
        conn.commit()
        sku_id = cursor.lastrowid
        conn.close()
        return sku_id

    def get_sku_stock(self, sku: str) -> Optional[int]:
        """Get available stock for a SKU."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        return row[0] if row else None

    def adjust_stock(self, sku: str, amount: int) -> Optional[int]:
        """Adjust stock level by amount (can be positive or negative)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
            (amount, sku),
        )
        conn.commit()

        cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        return row[0] if row else None

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> int:
        """Create a new reservation."""
        conn = self._get_connection()
        cursor = conn.cursor()

        created_at = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO reservations (sku, quantity, status, idempotency_key, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sku, quantity, "PENDING", idempotency_key, created_at),
        )
        conn.commit()
        reservation_id = cursor.lastrowid
        conn.close()
        return reservation_id

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[dict]:
        """Get a reservation by idempotency key."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, sku, quantity, status, idempotency_key, created_at FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        row = cursor.fetchone()
        conn.close()

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

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        """Get a reservation by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, sku, quantity, status, idempotency_key, created_at FROM reservations WHERE id = ?",
            (reservation_id,),
        )
        row = cursor.fetchone()
        conn.close()

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

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        """Update reservation status."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?", (status, reservation_id)
        )
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success

    def create_order(self, reservation_id: int, sku: str, quantity: int) -> int:
        """Create a new order."""
        conn = self._get_connection()
        cursor = conn.cursor()

        created_at = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "INSERT INTO orders (reservation_id, sku, quantity, created_at) VALUES (?, ?, ?, ?)",
            (reservation_id, sku, quantity, created_at),
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()
        return order_id

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        """Get paginated orders."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM orders")
        total = cursor.fetchone()[0]

        offset = (page - 1) * size
        cursor.execute(
            "SELECT id, reservation_id, sku, quantity, created_at FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
            (size, offset),
        )
        rows = cursor.fetchall()
        conn.close()

        orders = [
            {
                "id": row[0],
                "reservation_id": row[1],
                "sku": row[2],
                "quantity": row[3],
                "created_at": row[4],
            }
            for row in rows
        ]
        return orders, total

    def clear_all(self) -> None:
        """Clear all tables (for testing)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM orders")
        cursor.execute("DELETE FROM reservations")
        cursor.execute("DELETE FROM skus")
        conn.commit()
        conn.close()
