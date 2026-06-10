import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional, Generator

from .models import ReservationStatus, OrderStatus


class Database:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
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

    def _init_db(self) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    current_stock INTEGER NOT NULL DEFAULT 0,
                    reserved_stock INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus (id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    reservation_id INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus (id),
                    FOREIGN KEY (reservation_id) REFERENCES reservations (id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_reservations_idempotency
                ON reservations (idempotency_key)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_sku
                ON orders (sku_id)
            """)

    def create_sku(self, code: str, name: str, initial_stock: int) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO skus (code, name, current_stock, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (code, name, initial_stock, datetime.utcnow().isoformat()),
            )
            return cursor.lastrowid

    def get_sku(self, sku_id: int) -> Optional[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM skus WHERE id = ?", (sku_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def adjust_stock(self, sku_id: int, quantity: int) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET current_stock = current_stock + ? WHERE id = ?",
                (quantity, sku_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"SKU {sku_id} not found")

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str
    ) -> int:
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=15)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO reservations
                (sku_id, quantity, status, idempotency_key, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    sku_id,
                    quantity,
                    ReservationStatus.PENDING.value,
                    idempotency_key,
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            return cursor.lastrowid

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM reservations WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_reservation_status(
        self, reservation_id: int, status: ReservationStatus
    ) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status.value, reservation_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Reservation {reservation_id} not found")

    def update_reserved_stock(self, sku_id: int, quantity: int) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET reserved_stock = reserved_stock + ? WHERE id = ?",
                (quantity, sku_id),
            )

    def create_order(
        self, sku_id: int, quantity: int, reservation_id: Optional[int] = None
    ) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO orders (sku_id, quantity, status, reservation_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    sku_id,
                    quantity,
                    OrderStatus.PENDING.value,
                    reservation_id,
                    datetime.utcnow().isoformat(),
                ),
            )
            return cursor.lastrowid

    def get_order(self, order_id: int) -> Optional[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_orders(self, offset: int = 0, limit: int = 20) -> tuple[list[dict], int]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM orders")
            total = cursor.fetchone()["count"]

            cursor.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            items = [dict(row) for row in cursor.fetchall()]
            return items, total

    def get_expired_reservations(self) -> list[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """
                SELECT * FROM reservations
                WHERE status = ? AND expires_at < ?
                """,
                (ReservationStatus.PENDING.value, now),
            )
            return [dict(row) for row in cursor.fetchall()]

    def expire_reservation(self, reservation_id: int) -> None:
        self.update_reservation_status(
            reservation_id, ReservationStatus.EXPIRED
        )
