"""Database repository layer - all SQL operations."""
import sqlite3
from datetime import datetime
from contextlib import contextmanager
from typing import Optional


class Database:
    """SQLite database manager."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.init_db()

    @contextmanager
    def get_connection(self):
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

    def init_db(self):
        """Initialize database schema."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT UNIQUE NOT NULL,
                    available_stock INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reservation_id INTEGER NOT NULL UNIQUE,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (reservation_id) REFERENCES reservations(id),
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                )
            """)

            conn.commit()

    def create_sku(self, sku: str, initial_stock: int) -> int:
        """Create a new SKU with initial stock."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                "INSERT INTO skus (sku, available_stock, created_at) VALUES (?, ?, ?)",
                (sku, initial_stock, now)
            )
            return cursor.lastrowid

    def get_sku_stock(self, sku: str) -> Optional[int]:
        """Get available stock for a SKU."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return row[0] if row else None

    def adjust_stock(self, sku: str, amount: int) -> int:
        """Adjust stock level (positive or negative). Returns new stock level."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
                (amount, sku)
            )
            cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return row[0] if row else 0

    def check_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        """Check if idempotency key already exists. Returns existing reservation data if found."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, sku, quantity, status, created_at, idempotency_key
                   FROM reservations WHERE idempotency_key = ?""",
                (idempotency_key,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "sku": row[1],
                    "quantity": row[2],
                    "status": row[3],
                    "created_at": row[4],
                    "idempotency_key": row[5],
                }
            return None

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> int:
        """Create a new reservation. Assumes stock has been checked."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """INSERT INTO reservations
                   (sku, quantity, status, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (sku, quantity, "PENDING", idempotency_key, now)
            )
            return cursor.lastrowid

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        """Get reservation details by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, sku, quantity, status, created_at, idempotency_key
                   FROM reservations WHERE id = ?""",
                (reservation_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "sku": row[1],
                    "quantity": row[2],
                    "status": row[3],
                    "created_at": row[4],
                    "idempotency_key": row[5],
                }
            return None

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        """Update reservation status. Returns True if updated."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id)
            )
            return cursor.rowcount > 0

    def create_order(self, reservation_id: int, sku: str, quantity: int) -> int:
        """Create an order from a confirmed reservation."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """INSERT INTO orders (reservation_id, sku, quantity, created_at)
                   VALUES (?, ?, ?, ?)""",
                (reservation_id, sku, quantity, now)
            )
            return cursor.lastrowid

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        """Get paginated list of orders. Returns (orders, total_count)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM orders")
            total = cursor.fetchone()[0]

            offset = (page - 1) * size
            cursor.execute(
                """SELECT id, reservation_id, sku, quantity, created_at
                   FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (size, offset)
            )
            rows = cursor.fetchall()
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
