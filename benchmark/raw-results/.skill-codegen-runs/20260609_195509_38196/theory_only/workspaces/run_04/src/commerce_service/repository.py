import sqlite3
from datetime import datetime, timedelta, UTC
from typing import Optional
from contextlib import contextmanager


class Database:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        if db_path == ":memory:":
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        else:
            self._conn = None
        self._initialize()

    def _initialize(self):
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    quantity_available INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending',
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'reserved',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus(id)
                )
            """)
            conn.commit()

    @contextmanager
    def _connection(self):
        if self._conn:
            yield self._conn
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    def create_sku(self, name: str, quantity: int) -> int:
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT INTO skus (name, quantity_available) VALUES (?, ?)",
                (name, quantity),
            )
            conn.commit()
            return cursor.lastrowid

    def get_sku(self, sku_id: int) -> Optional[dict]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT id, name, quantity_available FROM skus WHERE id = ?",
                (sku_id,),
            ).fetchone()
            return dict(row) if row else None

    def adjust_stock(self, sku_id: int, delta: int) -> bool:
        with self._connection() as conn:
            sku = conn.execute(
                "SELECT quantity_available FROM skus WHERE id = ?",
                (sku_id,),
            ).fetchone()
            if not sku:
                return False
            new_quantity = sku["quantity_available"] + delta
            if new_quantity < 0:
                return False
            conn.execute(
                "UPDATE skus SET quantity_available = ? WHERE id = ?",
                (new_quantity, sku_id),
            )
            conn.commit()
            return True

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str
    ) -> Optional[int]:
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=15)
        with self._connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO reservations
                    (sku_id, quantity, idempotency_key, status, expires_at, created_at)
                    VALUES (?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        sku_id,
                        quantity,
                        idempotency_key,
                        expires_at.isoformat(),
                        now.isoformat(),
                    ),
                )
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                return None

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, sku_id, quantity, status, expires_at, created_at
                FROM reservations WHERE id = ?
                """,
                (reservation_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[dict]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, sku_id, quantity, status, expires_at, created_at
                FROM reservations WHERE idempotency_key = ?
                """,
                (key,),
            ).fetchone()
            return dict(row) if row else None

    def get_available_stock(self, sku_id: int) -> int:
        with self._connection() as conn:
            sku = conn.execute(
                "SELECT quantity_available FROM skus WHERE id = ?",
                (sku_id,),
            ).fetchone()
            if not sku:
                return 0
            quantity = sku["quantity_available"]
            pending = conn.execute(
                """
                SELECT COALESCE(SUM(quantity), 0) as total
                FROM reservations
                WHERE sku_id = ? AND status = 'pending' AND expires_at > ?
                """,
                (sku_id, datetime.now(UTC).isoformat()),
            ).fetchone()
            return quantity - pending["total"]

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> bool:
        with self._connection() as conn:
            conn.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id),
            )
            conn.commit()
            return True

    def create_order(self, sku_id: int, quantity: int) -> int:
        now = datetime.now(UTC)
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO orders (sku_id, quantity, status, created_at)
                VALUES (?, ?, 'confirmed', ?)
                """,
                (sku_id, quantity, now.isoformat()),
            )
            conn.commit()
            return cursor.lastrowid

    def get_orders(self, skip: int = 0, limit: int = 10) -> tuple[list[dict], int]:
        with self._connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as count FROM orders WHERE status = 'confirmed'"
            ).fetchone()["count"]
            rows = conn.execute(
                """
                SELECT id, sku_id, quantity, status, created_at
                FROM orders WHERE status = 'confirmed'
                ORDER BY created_at DESC LIMIT ? OFFSET ?
                """,
                (limit, skip),
            ).fetchall()
            return [dict(row) for row in rows], total

    def delete_reservation(self, reservation_id: int) -> bool:
        with self._connection() as conn:
            conn.execute(
                "DELETE FROM reservations WHERE id = ?",
                (reservation_id,),
            )
            conn.commit()
            return True
