"""Data access layer for commerce service."""

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

DATABASE_PATH = Path(__file__).parent / "commerce.db"
_lock = threading.Lock()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database schema."""
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                stock INTEGER NOT NULL CHECK (stock >= 0)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                idempotency_key TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id),
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        """)

        conn.commit()
        conn.close()


class Repository:
    def __init__(self):
        self.lock = _lock

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock."""
        with self.lock:
            conn = get_connection()
            cursor = conn.cursor()

            try:
                cursor.execute(
                    "INSERT INTO skus (sku, stock) VALUES (?, ?)",
                    (sku, initial_stock)
                )
                conn.commit()
                sku_id = cursor.lastrowid
                return {"id": sku_id, "sku": sku, "stock": initial_stock}
            finally:
                conn.close()

    def get_sku_stock(self, sku: str) -> Optional[int]:
        """Get current stock for a SKU."""
        with self.lock:
            conn = get_connection()
            cursor = conn.cursor()

            try:
                cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
                row = cursor.fetchone()
                return row["stock"] if row else None
            finally:
                conn.close()

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        """Adjust stock for a SKU."""
        with self.lock:
            conn = get_connection()
            cursor = conn.cursor()

            try:
                cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
                row = cursor.fetchone()

                if not row:
                    return None

                previous_stock = row["stock"]
                new_stock = previous_stock + amount

                if new_stock < 0:
                    return None

                cursor.execute(
                    "UPDATE skus SET stock = ? WHERE sku = ?",
                    (new_stock, sku)
                )
                conn.commit()

                return {
                    "sku": sku,
                    "previous_stock": previous_stock,
                    "new_stock": new_stock,
                    "adjustment": amount
                }
            finally:
                conn.close()

    def find_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[dict]:
        """Find a reservation by idempotency key."""
        with self.lock:
            conn = get_connection()
            cursor = conn.cursor()

            try:
                cursor.execute(
                    "SELECT id, sku, quantity, status, created_at FROM reservations WHERE idempotency_key = ?",
                    (idempotency_key,)
                )
                row = cursor.fetchone()

                if not row:
                    return None

                return {
                    "id": row["id"],
                    "sku": row["sku"],
                    "quantity": row["quantity"],
                    "status": row["status"],
                    "created_at": row["created_at"]
                }
            finally:
                conn.close()

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str
    ) -> dict:
        """Create a reservation."""
        with self.lock:
            conn = get_connection()
            cursor = conn.cursor()

            try:
                created_at = datetime.utcnow().isoformat()

                cursor.execute(
                    """INSERT INTO reservations (sku, quantity, idempotency_key, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (sku, quantity, idempotency_key, created_at)
                )
                conn.commit()
                reservation_id = cursor.lastrowid

                return {
                    "id": reservation_id,
                    "sku": sku,
                    "quantity": quantity,
                    "status": "PENDING",
                    "created_at": created_at
                }
            finally:
                conn.close()

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        """Get a reservation by ID."""
        with self.lock:
            conn = get_connection()
            cursor = conn.cursor()

            try:
                cursor.execute(
                    "SELECT id, sku, quantity, status, created_at FROM reservations WHERE id = ?",
                    (reservation_id,)
                )
                row = cursor.fetchone()

                if not row:
                    return None

                return {
                    "id": row["id"],
                    "sku": row["sku"],
                    "quantity": row["quantity"],
                    "status": row["status"],
                    "created_at": row["created_at"]
                }
            finally:
                conn.close()

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> bool:
        """Update reservation status."""
        with self.lock:
            conn = get_connection()
            cursor = conn.cursor()

            try:
                cursor.execute(
                    "UPDATE reservations SET status = ? WHERE id = ?",
                    (status, reservation_id)
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def set_reservation_created_at(
        self, reservation_id: int, created_at: str
    ) -> bool:
        """Update reservation created_at (used for testing expiration)."""
        with self.lock:
            conn = get_connection()
            cursor = conn.cursor()

            try:
                cursor.execute(
                    "UPDATE reservations SET created_at = ? WHERE id = ?",
                    (created_at, reservation_id)
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def create_order(
        self, reservation_id: int, sku: str, quantity: int
    ) -> dict:
        """Create an order from a reservation."""
        with self.lock:
            conn = get_connection()
            cursor = conn.cursor()

            try:
                created_at = datetime.utcnow().isoformat()

                cursor.execute(
                    """INSERT INTO orders (reservation_id, sku, quantity, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (reservation_id, sku, quantity, created_at)
                )
                conn.commit()
                order_id = cursor.lastrowid

                return {
                    "id": order_id,
                    "reservation_id": reservation_id,
                    "sku": sku,
                    "quantity": quantity,
                    "created_at": created_at
                }
            finally:
                conn.close()

    def list_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        """List orders with pagination."""
        with self.lock:
            conn = get_connection()
            cursor = conn.cursor()

            try:
                cursor.execute("SELECT COUNT(*) as total FROM orders")
                total = cursor.fetchone()["total"]

                offset = (page - 1) * size
                cursor.execute(
                    "SELECT id, reservation_id, sku, quantity, created_at FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
                    (size, offset)
                )
                rows = cursor.fetchall()

                orders = [
                    {
                        "id": row["id"],
                        "reservation_id": row["reservation_id"],
                        "sku": row["sku"],
                        "quantity": row["quantity"],
                        "created_at": row["created_at"]
                    }
                    for row in rows
                ]

                return orders, total
            finally:
                conn.close()
