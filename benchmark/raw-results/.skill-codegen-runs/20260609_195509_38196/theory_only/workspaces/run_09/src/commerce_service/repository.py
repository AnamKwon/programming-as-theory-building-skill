"""Database access layer."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .models import OrderStatus, ReservationStatus


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    reservation_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (sku_id) REFERENCES skus(id),
                    FOREIGN KEY (reservation_id) REFERENCES reservations(id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reservations_idempotency ON reservations(idempotency_key)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_orders_reservation_id ON orders(reservation_id)"
            )
            conn.commit()

    @contextmanager
    def _conn(self):
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # SKU operations
    def create_sku(self, name: str, quantity: int) -> int:
        """Create a new SKU."""
        with self._conn() as conn:
            cursor = conn.execute(
                "INSERT INTO skus (name, quantity) VALUES (?, ?)",
                (name, quantity),
            )
            conn.commit()
            return cursor.lastrowid

    def get_sku(self, sku_id: int) -> Optional[dict]:
        """Get SKU by ID."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, name, quantity FROM skus WHERE id = ?",
                (sku_id,),
            ).fetchone()
            return dict(row) if row else None

    def adjust_stock(self, sku_id: int, delta: int) -> bool:
        """Adjust stock level. Returns True if successful."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT quantity FROM skus WHERE id = ?",
                (sku_id,),
            ).fetchone()
            if not row:
                return False

            new_quantity = row["quantity"] + delta
            if new_quantity < 0:
                return False

            conn.execute(
                "UPDATE skus SET quantity = ? WHERE id = ?",
                (new_quantity, sku_id),
            )
            conn.commit()
            return True

    # Reservation operations
    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str, ttl_minutes: int = 30
    ) -> int:
        """Create a new reservation."""
        expires_at = (datetime.utcnow() + timedelta(minutes=ttl_minutes)).isoformat()
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reservations (sku_id, quantity, status, idempotency_key, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    sku_id,
                    quantity,
                    ReservationStatus.PENDING.value,
                    idempotency_key,
                    expires_at,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        """Get reservation by ID."""
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, sku_id, quantity, status, created_at, expires_at
                FROM reservations WHERE id = ?
                """,
                (reservation_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[dict]:
        """Get reservation by idempotency key."""
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, sku_id, quantity, status, created_at, expires_at
                FROM reservations WHERE idempotency_key = ?
                """,
                (key,),
            ).fetchone()
            return dict(row) if row else None

    def update_reservation_status(
        self, reservation_id: int, status: ReservationStatus
    ) -> bool:
        """Update reservation status."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status.value, reservation_id),
            )
            conn.commit()
            return True

    def get_expired_reservations(self) -> list[dict]:
        """Get all expired pending reservations."""
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, sku_id, quantity FROM reservations
                WHERE status = ? AND expires_at < ?
                """,
                (ReservationStatus.PENDING.value, now),
            ).fetchall()
            return [dict(row) for row in rows]

    # Order operations
    def create_order(
        self,
        sku_id: int,
        quantity: int,
        status: OrderStatus,
        reservation_id: Optional[int] = None,
    ) -> int:
        """Create a new order."""
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO orders (sku_id, quantity, status, reservation_id)
                VALUES (?, ?, ?, ?)
                """,
                (sku_id, quantity, status.value, reservation_id),
            )
            conn.commit()
            return cursor.lastrowid

    def get_order(self, order_id: int) -> Optional[dict]:
        """Get order by ID."""
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, sku_id, quantity, status, created_at
                FROM orders WHERE id = ?
                """,
                (order_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_orders(self, offset: int = 0, limit: int = 20) -> tuple[list[dict], int]:
        """List orders with pagination."""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) as count FROM orders").fetchone()[
                "count"
            ]
            rows = conn.execute(
                """
                SELECT id, sku_id, quantity, status, created_at
                FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
            return [dict(row) for row in rows], total

    def update_order_status(self, order_id: int, status: OrderStatus) -> bool:
        """Update order status."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE orders SET status = ? WHERE id = ?",
                (status.value, order_id),
            )
            conn.commit()
            return True

    def clear_all(self) -> None:
        """Clear all data (for testing)."""
        with self._conn() as conn:
            conn.execute("DELETE FROM orders")
            conn.execute("DELETE FROM reservations")
            conn.execute("DELETE FROM skus")
            conn.commit()
