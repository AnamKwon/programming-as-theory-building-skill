"""Data access layer for the commerce service."""

import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from uuid import uuid4


class Database:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # SKU table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS skus (
                    sku_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

            # Inventory table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS inventory (
                    sku_id TEXT PRIMARY KEY,
                    available_quantity INTEGER NOT NULL,
                    reserved_quantity INTEGER NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
                )
                """
            )

            # Reservations table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS reservations (
                    reservation_id TEXT PRIMARY KEY,
                    sku_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
                )
                """
            )

            # Orders table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    sku_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reservation_id TEXT,
                    FOREIGN KEY (sku_id) REFERENCES skus(sku_id),
                    FOREIGN KEY (reservation_id) REFERENCES reservations(reservation_id)
                )
                """
            )

            conn.commit()

    def _get_conn(self):
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # SKU operations

    def create_sku(self, sku_id: str, name: str, price: float) -> bool:
        """Create a new SKU. Returns True if created, False if already exists."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                now = datetime.utcnow().isoformat()
                cursor.execute(
                    "INSERT INTO skus (sku_id, name, price, created_at) VALUES (?, ?, ?, ?)",
                    (sku_id, name, price, now),
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def get_sku(self, sku_id: str) -> Optional[dict]:
        """Get SKU by ID."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM skus WHERE sku_id = ?", (sku_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # Inventory operations

    def set_inventory(self, sku_id: str, available: int, reserved: int = 0):
        """Set inventory quantities."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO inventory (sku_id, available_quantity, reserved_quantity) VALUES (?, ?, ?)",
                (sku_id, available, reserved),
            )
            conn.commit()

    def get_inventory(self, sku_id: str) -> Optional[dict]:
        """Get inventory for a SKU."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM inventory WHERE sku_id = ?", (sku_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def adjust_inventory(self, sku_id: str, delta: int) -> bool:
        """Adjust available inventory. Returns True if successful."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE inventory SET available_quantity = available_quantity + ? WHERE sku_id = ?",
                (delta, sku_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def reserve_inventory(self, sku_id: str, quantity: int) -> bool:
        """Reserve inventory. Returns True if successful."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE inventory
                SET available_quantity = available_quantity - ?,
                    reserved_quantity = reserved_quantity + ?
                WHERE sku_id = ? AND available_quantity >= ?
                """,
                (quantity, quantity, sku_id, quantity),
            )
            conn.commit()
            return cursor.rowcount > 0

    def release_reservation(self, sku_id: str, quantity: int) -> bool:
        """Release reserved inventory back to available."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE inventory
                SET available_quantity = available_quantity + ?,
                    reserved_quantity = reserved_quantity - ?
                WHERE sku_id = ? AND reserved_quantity >= ?
                """,
                (quantity, quantity, sku_id, quantity),
            )
            conn.commit()
            return cursor.rowcount > 0

    def confirm_reservation(self, sku_id: str, quantity: int) -> bool:
        """Convert reserved inventory to confirmed order."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE inventory
                SET reserved_quantity = reserved_quantity - ?
                WHERE sku_id = ? AND reserved_quantity >= ?
                """,
                (quantity, sku_id, quantity),
            )
            conn.commit()
            return cursor.rowcount > 0

    # Reservation operations

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str
    ) -> str:
        """Create a new reservation. Returns reservation_id."""
        reservation_id = str(uuid4())
        now = datetime.utcnow()
        expires_at = (now + timedelta(minutes=5)).isoformat()

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO reservations
                (reservation_id, sku_id, quantity, status, created_at, expires_at, idempotency_key)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reservation_id,
                    sku_id,
                    quantity,
                    "pending",
                    now.isoformat(),
                    expires_at,
                    idempotency_key,
                ),
            )
            conn.commit()
        return reservation_id

    def get_reservation(self, reservation_id: str) -> Optional[dict]:
        """Get reservation by ID."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reservations WHERE reservation_id = ?", (reservation_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        """Get reservation by idempotency key."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM reservations WHERE idempotency_key = ?", (idempotency_key,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_reservation_status(self, reservation_id: str, status: str) -> bool:
        """Update reservation status."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE reservation_id = ?",
                (status, reservation_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def expire_old_reservations(self) -> int:
        """Mark expired reservations. Returns count of expired reservations."""
        now = datetime.utcnow().isoformat()
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE reservations
                SET status = ?
                WHERE status = ? AND expires_at < ?
                """,
                ("expired", "pending", now),
            )
            conn.commit()
            return cursor.rowcount

    # Order operations

    def create_order(self, sku_id: str, quantity: int, reservation_id: str) -> str:
        """Create a new order. Returns order_id."""
        order_id = str(uuid4())
        now = datetime.utcnow().isoformat()

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO orders
                (order_id, sku_id, quantity, status, created_at, reservation_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (order_id, sku_id, quantity, "confirmed", now, reservation_id),
            )
            conn.commit()
        return order_id

    def get_order(self, order_id: str) -> Optional[dict]:
        """Get order by ID."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_orders(self, skip: int = 0, limit: int = 10) -> Tuple[List[dict], int]:
        """List orders with pagination. Returns (orders, total_count)."""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # Get total count
            cursor.execute("SELECT COUNT(*) FROM orders")
            total = cursor.fetchone()[0]

            # Get paginated results
            cursor.execute(
                """
                SELECT * FROM orders
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, skip),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows], total
