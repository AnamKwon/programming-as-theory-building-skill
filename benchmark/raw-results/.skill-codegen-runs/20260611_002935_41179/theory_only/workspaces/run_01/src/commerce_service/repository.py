"""Database repository layer for commerce service."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


DB_PATH = Path("commerce.db")


def init_db() -> None:
    """Initialize database schema."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skus (
            sku TEXT PRIMARY KEY,
            stock INTEGER NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            idempotency_key TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY (sku) REFERENCES skus(sku)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY (reservation_id) REFERENCES reservations(id)
        )
    """)

    conn.commit()
    conn.close()


class Repository:
    """Data access layer for commerce service."""

    def __init__(self):
        self.db_path = DB_PATH

    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # SKU operations

    def create_sku(self, sku: str, initial_stock: int) -> None:
        """Create a new SKU with initial stock."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO skus (sku, stock) VALUES (?, ?)",
                (sku, initial_stock)
            )
            conn.commit()
        finally:
            conn.close()

    def get_sku(self, sku: str) -> Optional[dict]:
        """Get SKU by code."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT sku, stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_stock(self, sku: str, amount: int) -> int:
        """Update stock level by amount (positive or negative). Returns new stock."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE skus SET stock = stock + ? WHERE sku = ?",
                (amount, sku)
            )
            cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            new_stock = row[0] if row else 0
            conn.commit()
            return new_stock
        finally:
            conn.close()

    # Reservation operations

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str,
        created_at: datetime
    ) -> int:
        """Create a new reservation. Returns reservation ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO reservations (sku, quantity, idempotency_key, status, created_at)
                   VALUES (?, ?, ?, 'PENDING', ?)""",
                (sku, quantity, idempotency_key, created_at.isoformat())
            )
            reservation_id = cursor.lastrowid
            conn.commit()
            return reservation_id
        finally:
            conn.close()

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        """Get reservation by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """SELECT id, sku, quantity, idempotency_key, status, created_at
                   FROM reservations WHERE id = ?""",
                (reservation_id,)
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                result['created_at'] = datetime.fromisoformat(result['created_at'])
                return result
            return None
        finally:
            conn.close()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        """Get reservation by idempotency key."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """SELECT id, sku, quantity, idempotency_key, status, created_at
                   FROM reservations WHERE idempotency_key = ?""",
                (idempotency_key,)
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                result['created_at'] = datetime.fromisoformat(result['created_at'])
                return result
            return None
        finally:
            conn.close()

    def update_reservation_status(self, reservation_id: int, status: str) -> None:
        """Update reservation status."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id)
            )
            conn.commit()
        finally:
            conn.close()

    # Order operations

    def create_order(self, reservation_id: int, created_at: datetime) -> int:
        """Create a new order. Returns order ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
                (reservation_id, created_at.isoformat())
            )
            order_id = cursor.lastrowid
            conn.commit()
            return order_id
        finally:
            conn.close()

    def get_orders_paginated(self, page: int, size: int) -> Tuple[list[dict], int]:
        """Get paginated orders. Returns (orders, total_count)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM orders")
            total = cursor.fetchone()[0]

            offset = (page - 1) * size
            cursor.execute(
                """SELECT id, reservation_id, created_at FROM orders
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (size, offset)
            )
            rows = cursor.fetchall()
            orders = []
            for row in rows:
                result = dict(row)
                result['created_at'] = datetime.fromisoformat(result['created_at'])
                orders.append(result)

            return orders, total
        finally:
            conn.close()
