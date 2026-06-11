"""Database access layer."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


class Repository:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sku_inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL UNIQUE,
                available_stock INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                idempotency_key TEXT UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES sku_inventory(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            )
        """)

        conn.commit()
        conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_sku(self, sku: str, initial_stock: int) -> int:
        """Create a new SKU with initial stock."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO sku_inventory (sku, available_stock) VALUES (?, ?)",
                (sku, initial_stock),
            )
            conn.commit()
            sku_id = cursor.lastrowid
            return sku_id
        finally:
            conn.close()

    def get_sku_by_name(self, sku: str) -> Optional[dict]:
        """Get SKU info by name."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, sku, available_stock FROM sku_inventory WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def adjust_stock(self, sku: str, amount: int) -> int:
        """Adjust stock for a SKU. Returns new stock level."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE sku_inventory SET available_stock = available_stock + ? WHERE sku = ?",
                (amount, sku),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"SKU not found: {sku}")
            conn.commit()

            cursor.execute("SELECT available_stock FROM sku_inventory WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return row[0]
        finally:
            conn.close()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        """Get reservation by idempotency key."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """SELECT r.id, r.sku_id, r.quantity, r.status, r.created_at, r.idempotency_key,
                          s.sku
                   FROM reservations r
                   JOIN sku_inventory s ON r.sku_id = s.id
                   WHERE r.idempotency_key = ?""",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_reservation(
        self, sku_id: int, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        """Create a new reservation and deduct stock."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """INSERT INTO reservations (sku_id, quantity, status, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (sku_id, quantity, "PENDING", idempotency_key, now),
            )
            conn.commit()
            reservation_id = cursor.lastrowid

            cursor.execute(
                "UPDATE sku_inventory SET available_stock = available_stock - ? WHERE id = ?",
                (quantity, sku_id),
            )
            conn.commit()

            return {
                "id": reservation_id,
                "sku": sku,
                "quantity": quantity,
                "status": "PENDING",
                "created_at": now,
                "idempotency_key": idempotency_key,
            }
        finally:
            conn.close()

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        """Get reservation by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """SELECT r.id, r.sku_id, r.quantity, r.status, r.created_at, r.idempotency_key,
                          s.sku
                   FROM reservations r
                   JOIN sku_inventory s ON r.sku_id = s.id
                   WHERE r.id = ?""",
                (reservation_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        """Update reservation status."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def create_order(self, reservation_id: int) -> int:
        """Create an order for a confirmed reservation."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            now = datetime.utcnow().isoformat()
            cursor.execute(
                "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
                (reservation_id, now),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_order(self, order_id: int) -> Optional[dict]:
        """Get order by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, reservation_id, created_at FROM orders WHERE id = ?",
                (order_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        """List orders with pagination. Returns (orders, total_count)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM orders")
            total = cursor.fetchone()[0]

            offset = (page - 1) * size
            cursor.execute(
                "SELECT id, reservation_id, created_at FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
                (size, offset),
            )
            rows = cursor.fetchall()
            orders = [dict(row) for row in rows]
            return orders, total
        finally:
            conn.close()

    def restore_stock(self, sku_id: int, quantity: int) -> None:
        """Restore stock to a SKU."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE sku_inventory SET available_stock = available_stock + ? WHERE id = ?",
                (quantity, sku_id),
            )
            conn.commit()
        finally:
            conn.close()
