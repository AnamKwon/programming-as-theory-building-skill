"""Data access layer for commerce service."""

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


class Repository:
    """SQLite-backed repository for commerce data."""

    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = Path(db_path)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        """Initialize database schema."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                sku_id TEXT PRIMARY KEY,
                stock INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                reservation_id TEXT PRIMARY KEY,
                sku_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                sku_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reservations_idempotency
            ON reservations(idempotency_key, sku_id)
        """)

        conn.commit()
        conn.close()

    # SKU operations
    def create_sku(self, sku_id: str, initial_stock: int) -> dict:
        """Create a new SKU."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO skus (sku_id, stock, created_at) VALUES (?, ?, ?)",
                (sku_id, initial_stock, now),
            )
            conn.commit()
            return {
                "sku_id": sku_id,
                "stock": initial_stock,
                "created_at": now,
            }
        finally:
            conn.close()

    def get_sku(self, sku_id: str) -> dict | None:
        """Get SKU by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM skus WHERE sku_id = ?", (sku_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def adjust_stock(self, sku_id: str, delta: int) -> dict | None:
        """Adjust stock for a SKU."""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "UPDATE skus SET stock = stock + ? WHERE sku_id = ?",
                (delta, sku_id),
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            cursor.execute("SELECT * FROM skus WHERE sku_id = ?", (sku_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # Reservation operations
    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str
    ) -> dict:
        """Create a new reservation."""
        reservation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=5)
        ).isoformat()

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO reservations
                (reservation_id, sku_id, quantity, status, idempotency_key, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reservation_id,
                    sku_id,
                    quantity,
                    "pending",
                    idempotency_key,
                    now,
                    expires_at,
                ),
            )
            conn.commit()
            return {
                "reservation_id": reservation_id,
                "sku_id": sku_id,
                "quantity": quantity,
                "status": "pending",
                "idempotency_key": idempotency_key,
                "created_at": now,
                "expires_at": expires_at,
            }
        finally:
            conn.close()

    def get_reservation(self, reservation_id: str) -> dict | None:
        """Get reservation by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT * FROM reservations WHERE reservation_id = ?",
                (reservation_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_reservation_by_idempotency(
        self, idempotency_key: str, sku_id: str
    ) -> dict | None:
        """Get reservation by idempotency key and SKU."""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT * FROM reservations
                WHERE idempotency_key = ? AND sku_id = ?
                LIMIT 1
                """,
                (idempotency_key, sku_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_reservation_status(
        self, reservation_id: str, status: str
    ) -> dict | None:
        """Update reservation status."""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE reservation_id = ?",
                (status, reservation_id),
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            cursor.execute(
                "SELECT * FROM reservations WHERE reservation_id = ?",
                (reservation_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # Order operations
    def create_order(
        self, sku_id: str, quantity: int, initial_status: str = "pending"
    ) -> dict:
        """Create a new order."""
        order_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO orders
                (order_id, sku_id, quantity, status, created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (order_id, sku_id, quantity, initial_status, now),
            )
            conn.commit()
            return {
                "order_id": order_id,
                "sku_id": sku_id,
                "quantity": quantity,
                "status": initial_status,
                "created_at": now,
                "completed_at": None,
            }
        finally:
            conn.close()

    def get_order(self, order_id: str) -> dict | None:
        """Get order by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[dict], int]:
        """List orders with pagination."""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT COUNT(*) FROM orders")
            total = cursor.fetchone()[0]

            cursor.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = cursor.fetchall()
            orders = [dict(row) for row in rows]
            return orders, total
        finally:
            conn.close()

    def update_order_status(
        self, order_id: str, status: str
    ) -> dict | None:
        """Update order status."""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            completed_at = (
                datetime.now(timezone.utc).isoformat()
                if status == "completed"
                else None
            )
            if completed_at:
                cursor.execute(
                    "UPDATE orders SET status = ?, completed_at = ? WHERE order_id = ?",
                    (status, completed_at, order_id),
                )
            else:
                cursor.execute(
                    "UPDATE orders SET status = ? WHERE order_id = ?",
                    (status, order_id),
                )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
