import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from commerce_service.models import OrderStatus, ReservationStatus


DB_PATH = Path("commerce.db")


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                current_stock INTEGER NOT NULL CHECK (current_stock >= 0)
            );

            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL REFERENCES skus(id),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                status TEXT NOT NULL DEFAULT 'pending',
                idempotency_key TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                confirmed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL REFERENCES reservations(id),
                sku_id INTEGER NOT NULL REFERENCES skus(id),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                confirmed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_reservations_idempotency_key
                ON reservations(idempotency_key);
            CREATE INDEX IF NOT EXISTS idx_orders_reservation_id
                ON orders(reservation_id);
        """)
        conn.commit()


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


class Repository:
    @staticmethod
    def create_sku(code: str, name: str, initial_stock: int) -> int:
        with get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO skus (code, name, current_stock) VALUES (?, ?, ?)",
                (code, name, initial_stock),
            )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def get_sku(sku_id: int) -> Optional[dict]:
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, code, name, current_stock FROM skus WHERE id = ?",
                (sku_id,),
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def adjust_stock(sku_id: int, quantity: int) -> bool:
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE skus SET current_stock = current_stock + ? WHERE id = ?",
                (quantity, sku_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def create_reservation(
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> int:
        with get_db() as conn:
            cursor = conn.execute(
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
                    created_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def get_reservation(reservation_id: int) -> Optional[dict]:
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT id, sku_id, quantity, status, idempotency_key,
                       created_at, expires_at, confirmed_at
                FROM reservations
                WHERE id = ?
                """,
                (reservation_id,),
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_reservation_by_idempotency_key(idempotency_key: str) -> Optional[dict]:
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT id, sku_id, quantity, status, idempotency_key,
                       created_at, expires_at, confirmed_at
                FROM reservations
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_reservation_status(
        reservation_id: int, status: ReservationStatus, confirmed_at: Optional[datetime] = None
    ) -> bool:
        with get_db() as conn:
            confirmed_at_str = confirmed_at.isoformat() if confirmed_at else None
            cursor = conn.execute(
                """
                UPDATE reservations
                SET status = ?, confirmed_at = ?
                WHERE id = ?
                """,
                (status.value, confirmed_at_str, reservation_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def create_order(
        reservation_id: int,
        sku_id: int,
        quantity: int,
        created_at: datetime,
    ) -> int:
        with get_db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO orders
                (reservation_id, sku_id, quantity, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    reservation_id,
                    sku_id,
                    quantity,
                    OrderStatus.PENDING.value,
                    created_at.isoformat(),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def get_order(order_id: int) -> Optional[dict]:
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT id, reservation_id, sku_id, quantity, status,
                       created_at, confirmed_at
                FROM orders
                WHERE id = ?
                """,
                (order_id,),
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_order_status(
        order_id: int, status: OrderStatus, confirmed_at: Optional[datetime] = None
    ) -> bool:
        with get_db() as conn:
            confirmed_at_str = confirmed_at.isoformat() if confirmed_at else None
            cursor = conn.execute(
                """
                UPDATE orders
                SET status = ?, confirmed_at = ?
                WHERE id = ?
                """,
                (status.value, confirmed_at_str, order_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def list_orders(offset: int = 0, limit: int = 20) -> tuple[list[dict], int]:
        with get_db() as conn:
            total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            rows = conn.execute(
                """
                SELECT id, reservation_id, sku_id, quantity, status,
                       created_at, confirmed_at
                FROM orders
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
            return [dict(row) for row in rows], total
