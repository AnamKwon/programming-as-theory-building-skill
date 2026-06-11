"""Database repository layer for inventory management."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional


DATABASE_PATH = Path(__file__).parent.parent.parent / "commerce.db"


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections."""
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database schema."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS sku (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                available_stock INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reservation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                confirmed_at TEXT,
                FOREIGN KEY (sku_id) REFERENCES sku(id)
            );

            CREATE TABLE IF NOT EXISTS "order" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservation(id),
                FOREIGN KEY (sku_id) REFERENCES sku(id)
            );

            CREATE INDEX IF NOT EXISTS idx_idempotency_key ON reservation(idempotency_key);
            CREATE INDEX IF NOT EXISTS idx_reservation_status ON reservation(status);
            CREATE INDEX IF NOT EXISTS idx_order_created_at ON "order"(created_at);
        """)
        conn.commit()


class Repository:
    """Data access layer for commerce service."""

    @staticmethod
    def create_sku(sku: str, initial_stock: int) -> int:
        """Create a new SKU with initial stock."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                "INSERT INTO sku (sku, available_stock, created_at) VALUES (?, ?, ?)",
                (sku, initial_stock, now),
            )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def get_sku_by_name(sku: str) -> Optional[dict]:
        """Get SKU by name."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, sku, available_stock, created_at FROM sku WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def adjust_stock(sku: str, amount: int) -> Optional[dict]:
        """Adjust stock level for a SKU."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sku SET available_stock = available_stock + ? WHERE sku = ?",
                (amount, sku),
            )
            if cursor.rowcount == 0:
                return None
            conn.commit()
            cursor.execute("SELECT available_stock FROM sku WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return {"sku": sku, "available_stock": row[0]} if row else None

    @staticmethod
    def create_reservation(
        sku_id: int, quantity: int, idempotency_key: str
    ) -> dict:
        """Create a new reservation."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """INSERT INTO reservation (sku_id, quantity, status, idempotency_key, created_at)
                   VALUES (?, ?, 'PENDING', ?, ?)""",
                (sku_id, quantity, idempotency_key, now),
            )
            conn.commit()
            reservation_id = cursor.lastrowid

            cursor.execute(
                """SELECT r.id, s.sku, r.quantity, r.status, r.idempotency_key, r.created_at
                   FROM reservation r
                   JOIN sku s ON r.sku_id = s.id
                   WHERE r.id = ?""",
                (reservation_id,),
            )
            row = cursor.fetchone()
            return dict(row)

    @staticmethod
    def get_reservation_by_idempotency_key(idempotency_key: str) -> Optional[dict]:
        """Get reservation by idempotency key."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT r.id, s.sku, r.quantity, r.status, r.idempotency_key, r.created_at
                   FROM reservation r
                   JOIN sku s ON r.sku_id = s.id
                   WHERE r.idempotency_key = ?""",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_reservation(reservation_id: int) -> Optional[dict]:
        """Get reservation by ID."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT r.id, s.sku, s.id as sku_id, r.quantity, r.status, r.idempotency_key, r.created_at, r.confirmed_at
                   FROM reservation r
                   JOIN sku s ON r.sku_id = s.id
                   WHERE r.id = ?""",
                (reservation_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_reservation_status(reservation_id: int, status: str) -> bool:
        """Update reservation status."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservation SET status = ? WHERE id = ?",
                (status, reservation_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def confirm_reservation(reservation_id: int) -> bool:
        """Confirm a reservation and set confirmed_at."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                "UPDATE reservation SET status = 'CONFIRMED', confirmed_at = ? WHERE id = ?",
                (now, reservation_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def deduct_stock(sku_id: int, quantity: int) -> bool:
        """Deduct stock for a SKU."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sku SET available_stock = available_stock - ? WHERE id = ?",
                (quantity, sku_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def restore_stock(sku_id: int, quantity: int) -> bool:
        """Restore stock for a SKU."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sku SET available_stock = available_stock + ? WHERE id = ?",
                (quantity, sku_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def create_order(reservation_id: int, sku_id: int, quantity: int) -> int:
        """Create an order from a confirmed reservation."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """INSERT INTO "order" (reservation_id, sku_id, quantity, created_at)
                   VALUES (?, ?, ?, ?)""",
                (reservation_id, sku_id, quantity, now),
            )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def get_orders(page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        """Get paginated orders."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            offset = (page - 1) * size

            cursor.execute("SELECT COUNT(*) FROM \"order\"")
            total = cursor.fetchone()[0]

            cursor.execute(
                """SELECT o.id, s.sku, o.quantity, o.created_at
                   FROM "order" o
                   JOIN sku s ON o.sku_id = s.id
                   ORDER BY o.created_at DESC
                   LIMIT ? OFFSET ?""",
                (size, offset),
            )
            rows = cursor.fetchall()
            orders = [dict(row) for row in rows]
            return orders, total

    @staticmethod
    def get_sku_id_by_name(sku: str) -> Optional[int]:
        """Get SKU ID by SKU name."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM sku WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return row[0] if row else None
