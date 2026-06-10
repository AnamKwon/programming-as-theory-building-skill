"""Database repository for inventory and orders."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from commerce_service.models import OrderStatus, ReservationStatus


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema."""
        with self._conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS stock (
                sku_id INTEGER PRIMARY KEY,
                quantity INTEGER NOT NULL DEFAULT 0,
                reserved INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                idempotency_key TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            );

            CREATE INDEX IF NOT EXISTS idx_reservations_order_id ON reservations(order_id);
            CREATE INDEX IF NOT EXISTS idx_reservations_sku_id ON reservations(sku_id);
            CREATE INDEX IF NOT EXISTS idx_reservations_idempotency_key ON reservations(idempotency_key);
            CREATE INDEX IF NOT EXISTS idx_stock_sku_id ON stock(sku_id);
            """)

    def create_sku(self, code: str, name: str) -> int:
        """Create a new SKU."""
        with self._conn() as conn:
            cursor = conn.execute(
                "INSERT INTO skus (code, name) VALUES (?, ?)",
                (code, name)
            )
            return cursor.lastrowid

    def get_sku(self, sku_id: int) -> Optional[dict]:
        """Get SKU by ID."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, code, name FROM skus WHERE id = ?",
                (sku_id,)
            ).fetchone()
            return dict(row) if row else None

    def adjust_stock(self, sku_id: int, quantity: int) -> bool:
        """Adjust stock quantity. Returns True if successful."""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO stock (sku_id, quantity) VALUES (?, 0)",
                (sku_id,)
            )
            row = conn.execute(
                "SELECT quantity, reserved FROM stock WHERE sku_id = ?",
                (sku_id,)
            ).fetchone()

            if not row:
                return False

            current, reserved = dict(row)["quantity"], dict(row)["reserved"]
            new_quantity = current + quantity

            if new_quantity < reserved:
                raise ValueError("Adjustment would result in negative available stock")

            conn.execute(
                "UPDATE stock SET quantity = ? WHERE sku_id = ?",
                (new_quantity, sku_id)
            )
            return True

    def get_stock(self, sku_id: int) -> Optional[dict]:
        """Get stock info for a SKU."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT sku_id, quantity, reserved FROM stock WHERE sku_id = ?",
                (sku_id,)
            ).fetchone()
            return dict(row) if row else None

    def create_order(self) -> int:
        """Create a new order."""
        with self._conn() as conn:
            cursor = conn.execute("INSERT INTO orders (status) VALUES ('pending')")
            return cursor.lastrowid

    def get_order(self, order_id: int) -> Optional[dict]:
        """Get order by ID."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, status, created_at FROM orders WHERE id = ?",
                (order_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_orders(self, skip: int = 0, limit: int = 20) -> tuple[list[dict], int]:
        """List orders with pagination."""
        with self._conn() as conn:
            total_row = conn.execute("SELECT COUNT(*) as count FROM orders").fetchone()
            total = dict(total_row)["count"]

            rows = conn.execute(
                "SELECT id, status, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, skip)
            ).fetchall()
            return [dict(row) for row in rows], total

    def get_order_reservations(self, order_id: int) -> list[dict]:
        """Get all reservations for an order."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT id, order_id, sku_id, quantity, status, created_at, expires_at
                   FROM reservations WHERE order_id = ? ORDER BY created_at ASC""",
                (order_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def create_reservation(
        self,
        order_id: int,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        expires_in_seconds: int,
    ) -> int:
        """Create a reservation. Raises ValueError if insufficient stock or key exists."""
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)

        with self._conn() as conn:
            stock_row = conn.execute(
                "SELECT quantity, reserved FROM stock WHERE sku_id = ?",
                (sku_id,)
            ).fetchone()

            if not stock_row:
                raise ValueError(f"SKU {sku_id} not found")

            stock_dict = dict(stock_row)
            available = stock_dict["quantity"] - stock_dict["reserved"]

            if available < quantity:
                raise ValueError(f"Insufficient stock: {available} available, {quantity} requested")

            cursor = conn.execute(
                """INSERT INTO reservations (order_id, sku_id, quantity, status, idempotency_key, expires_at)
                   VALUES (?, ?, ?, 'pending', ?, ?)""",
                (order_id, sku_id, quantity, idempotency_key, expires_at)
            )
            reservation_id = cursor.lastrowid

            conn.execute(
                "UPDATE stock SET reserved = reserved + ? WHERE sku_id = ?",
                (quantity, sku_id)
            )

            return reservation_id

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        """Get reservation by ID."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT id, order_id, sku_id, quantity, status, created_at, expires_at
                   FROM reservations WHERE id = ?""",
                (reservation_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        """Get reservation by idempotency key."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT id, order_id, sku_id, quantity, status, created_at, expires_at
                   FROM reservations WHERE idempotency_key = ?""",
                (idempotency_key,)
            ).fetchone()
            return dict(row) if row else None

    def confirm_reservation(self, reservation_id: int) -> bool:
        """Confirm a pending reservation. Returns True if successful."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT status, expires_at FROM reservations WHERE id = ?",
                (reservation_id,)
            ).fetchone()

            if not row:
                return False

            res_dict = dict(row)
            if res_dict["status"] != ReservationStatus.PENDING:
                raise ValueError(f"Cannot confirm reservation in {res_dict['status']} status")

            if datetime.fromisoformat(res_dict["expires_at"]) < datetime.utcnow():
                conn.execute(
                    "UPDATE reservations SET status = ? WHERE id = ?",
                    (ReservationStatus.EXPIRED, reservation_id)
                )
                raise ValueError("Reservation has expired")

            conn.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (ReservationStatus.CONFIRMED, reservation_id)
            )
            return True

    def cancel_reservation(self, reservation_id: int) -> bool:
        """Cancel a reservation. Returns True if successful."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT sku_id, quantity, status FROM reservations WHERE id = ?",
                (reservation_id,)
            ).fetchone()

            if not row:
                return False

            res_dict = dict(row)
            if res_dict["status"] not in (ReservationStatus.PENDING, ReservationStatus.CONFIRMED):
                raise ValueError(f"Cannot cancel reservation in {res_dict['status']} status")

            sku_id = res_dict["sku_id"]
            quantity = res_dict["quantity"]

            conn.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (ReservationStatus.CANCELLED, reservation_id)
            )
            conn.execute(
                "UPDATE stock SET reserved = reserved - ? WHERE sku_id = ?",
                (quantity, sku_id)
            )
            return True

    def update_order_status(self, order_id: int, status: str) -> bool:
        """Update order status."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE orders SET status = ? WHERE id = ?",
                (status, order_id)
            )
            return True

    def expire_old_reservations(self) -> int:
        """Mark expired reservations as expired and free their stock. Returns count."""
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            expired_rows = conn.execute(
                """SELECT id, sku_id, quantity FROM reservations
                   WHERE status = ? AND expires_at < ?""",
                (ReservationStatus.PENDING, now)
            ).fetchall()

            for row in expired_rows:
                expired_dict = dict(row)
                conn.execute(
                    "UPDATE reservations SET status = ? WHERE id = ?",
                    (ReservationStatus.EXPIRED, expired_dict["id"])
                )
                conn.execute(
                    "UPDATE stock SET reserved = reserved - ? WHERE sku_id = ?",
                    (expired_dict["quantity"], expired_dict["sku_id"])
                )

            return len(expired_rows)

    def cleanup_db(self):
        """Delete all data (for testing)."""
        with self._conn() as conn:
            conn.executescript("""
            DELETE FROM reservations;
            DELETE FROM stock;
            DELETE FROM orders;
            DELETE FROM skus;
            """)
