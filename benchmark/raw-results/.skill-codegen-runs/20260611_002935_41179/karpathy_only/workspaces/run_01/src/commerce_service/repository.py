"""Database repository layer for commerce service."""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


class Database:
    """Database connection and schema management."""

    def __init__(self, db_path: str = ":memory:"):
        """Initialize database."""
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None

    def get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                isolation_level=None,
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    def init_schema(self) -> None:
        """Initialize database schema."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sku (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL UNIQUE,
                available_stock INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (sku) REFERENCES sku(sku)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS "order" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservation(id)
            )
        """)

        conn.commit()


class SKURepository:
    """Repository for SKU operations."""

    def __init__(self, db: Database):
        """Initialize repository."""
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            """
            INSERT INTO sku (sku, available_stock, created_at)
            VALUES (?, ?, ?)
            """,
            (sku, initial_stock, now),
        )
        conn.commit()

        return {
            "sku": sku,
            "available_stock": initial_stock,
        }

    def get_sku(self, sku: str) -> Optional[dict]:
        """Get SKU by name."""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, sku, available_stock FROM sku WHERE sku = ?",
            (sku,),
        )
        row = cursor.fetchone()

        if row:
            return {
                "id": row[0],
                "sku": row[1],
                "available_stock": row[2],
            }
        return None

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        """Adjust stock level for a SKU."""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE sku SET available_stock = available_stock + ? WHERE sku = ?
            """,
            (amount, sku),
        )
        conn.commit()

        return self.get_sku(sku)


class ReservationRepository:
    """Repository for reservation operations."""

    def __init__(self, db: Database):
        """Initialize repository."""
        self.db = db

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str,
    ) -> dict:
        """Create a new reservation."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            """
            INSERT INTO reservation (sku, quantity, status, idempotency_key, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (sku, quantity, "PENDING", idempotency_key, now, now),
        )
        conn.commit()

        return {
            "id": cursor.lastrowid,
            "sku": sku,
            "quantity": quantity,
            "status": "PENDING",
            "created_at": now,
            "updated_at": now,
        }

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        """Get reservation by ID."""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, sku, quantity, status, created_at, updated_at
            FROM reservation WHERE id = ?
            """,
            (reservation_id,),
        )
        row = cursor.fetchone()

        if row:
            return {
                "id": row[0],
                "sku": row[1],
                "quantity": row[2],
                "status": row[3],
                "created_at": row[4],
                "updated_at": row[5],
            }
        return None

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[dict]:
        """Get reservation by idempotency key."""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, sku, quantity, status, created_at, updated_at
            FROM reservation WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        )
        row = cursor.fetchone()

        if row:
            return {
                "id": row[0],
                "sku": row[1],
                "quantity": row[2],
                "status": row[3],
                "created_at": row[4],
                "updated_at": row[5],
            }
        return None

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> Optional[dict]:
        """Update reservation status."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            """
            UPDATE reservation SET status = ?, updated_at = ? WHERE id = ?
            """,
            (status, now, reservation_id),
        )
        conn.commit()

        return self.get_reservation(reservation_id)


class OrderRepository:
    """Repository for order operations."""

    def __init__(self, db: Database):
        """Initialize repository."""
        self.db = db

    def create_order(self, reservation_id: int) -> dict:
        """Create a new order."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            """
            INSERT INTO "order" (reservation_id, created_at)
            VALUES (?, ?)
            """,
            (reservation_id, now),
        )
        conn.commit()

        return {
            "id": cursor.lastrowid,
            "reservation_id": reservation_id,
            "created_at": now,
        }

    def get_orders(self, offset: int = 0, limit: int = 10) -> Tuple[list, int]:
        """Get paginated orders."""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM \"order\"")
        total = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT id, reservation_id, created_at FROM "order"
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cursor.fetchall()

        orders = [
            {
                "id": row[0],
                "reservation_id": row[1],
                "created_at": row[2],
            }
            for row in rows
        ]

        return orders, total
