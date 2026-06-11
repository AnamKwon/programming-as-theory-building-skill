"""Database repository layer for inventory and orders."""

import sqlite3
import threading
from datetime import datetime
from typing import Optional

DATABASE_PATH = "commerce.db"
_lock = threading.Lock()


def get_connection():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Initialize database schema."""
    with _lock:
        conn = get_connection()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS skus (
                    sku TEXT PRIMARY KEY,
                    stock INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sku) REFERENCES skus (sku)
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reservation_id INTEGER NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (reservation_id) REFERENCES reservations (id)
                );

                CREATE INDEX IF NOT EXISTS idx_reservations_sku ON reservations(sku);
                CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
            """)
            conn.commit()
        finally:
            conn.close()


class Repository:
    """Data access layer for commerce operations."""

    def __init__(self):
        """Initialize repository."""
        pass

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock."""
        with _lock:
            conn = get_connection()
            try:
                conn.execute(
                    "INSERT INTO skus (sku, stock) VALUES (?, ?)",
                    (sku, initial_stock),
                )
                conn.commit()
                return {"sku": sku, "stock": initial_stock}
            finally:
                conn.close()

    def get_sku(self, sku: str) -> Optional[dict]:
        """Get SKU by identifier."""
        with _lock:
            conn = get_connection()
            try:
                row = conn.execute(
                    "SELECT sku, stock FROM skus WHERE sku = ?", (sku,)
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def adjust_stock(self, sku: str, amount: int) -> dict:
        """Adjust stock level for a SKU."""
        with _lock:
            conn = get_connection()
            try:
                conn.execute("UPDATE skus SET stock = stock + ? WHERE sku = ?", (amount, sku))
                conn.commit()
                row = conn.execute(
                    "SELECT sku, stock FROM skus WHERE sku = ?", (sku,)
                ).fetchone()
                return dict(row) if row else {}
            finally:
                conn.close()

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        """Create a new reservation."""
        with _lock:
            conn = get_connection()
            try:
                conn.execute(
                    "UPDATE skus SET stock = stock - ? WHERE sku = ?",
                    (quantity, sku),
                )
                now = datetime.utcnow().isoformat()
                cursor = conn.execute(
                    "INSERT INTO reservations (sku, quantity, idempotency_key, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (sku, quantity, idempotency_key, "PENDING", now),
                )
                conn.commit()
                reservation_id = cursor.lastrowid
                return {
                    "id": reservation_id,
                    "sku": sku,
                    "quantity": quantity,
                    "status": "PENDING",
                    "created_at": now,
                }
            finally:
                conn.close()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        """Get reservation by idempotency key."""
        with _lock:
            conn = get_connection()
            try:
                row = conn.execute(
                    "SELECT id, sku, quantity, status, created_at FROM reservations "
                    "WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        """Get reservation by ID."""
        with _lock:
            conn = get_connection()
            try:
                row = conn.execute(
                    "SELECT id, sku, quantity, status, created_at FROM reservations WHERE id = ?",
                    (reservation_id,),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def update_reservation_status(self, reservation_id: int, status: str) -> dict:
        """Update reservation status."""
        with _lock:
            conn = get_connection()
            try:
                conn.execute(
                    "UPDATE reservations SET status = ? WHERE id = ?",
                    (status, reservation_id),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT id, sku, quantity, status, created_at FROM reservations WHERE id = ?",
                    (reservation_id,),
                ).fetchone()
                return dict(row) if row else {}
            finally:
                conn.close()

    def restore_stock(self, sku: str, quantity: int) -> None:
        """Restore stock for a SKU."""
        with _lock:
            conn = get_connection()
            try:
                conn.execute("UPDATE skus SET stock = stock + ? WHERE sku = ?", (quantity, sku))
                conn.commit()
            finally:
                conn.close()

    def create_order(self, reservation_id: int) -> dict:
        """Create an order from a reservation."""
        with _lock:
            conn = get_connection()
            try:
                now = datetime.utcnow().isoformat()
                cursor = conn.execute(
                    "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
                    (reservation_id, now),
                )
                conn.commit()
                order_id = cursor.lastrowid
                return {
                    "id": order_id,
                    "reservation_id": reservation_id,
                    "created_at": now,
                }
            finally:
                conn.close()

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        """Get paginated orders."""
        with _lock:
            conn = get_connection()
            try:
                offset = (page - 1) * size
                rows = conn.execute(
                    "SELECT id, reservation_id, created_at FROM orders "
                    "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (size, offset),
                ).fetchall()
                total = conn.execute("SELECT COUNT(*) as count FROM orders").fetchone()[
                    "count"
                ]
                return [dict(row) for row in rows], total
            finally:
                conn.close()
