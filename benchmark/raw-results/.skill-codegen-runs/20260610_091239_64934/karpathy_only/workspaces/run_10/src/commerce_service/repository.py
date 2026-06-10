import sqlite3
import uuid
from datetime import datetime, timedelta
from contextlib import contextmanager
from .models import ReservationState, OrderState


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self):
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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS skus (
                    sku TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS stock (
                    sku TEXT PRIMARY KEY,
                    available_quantity INTEGER NOT NULL DEFAULT 0,
                    reserved_quantity INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                );
                CREATE TABLE IF NOT EXISTS reservations (
                    id TEXT PRIMARY KEY,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                );
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                );
                CREATE INDEX IF NOT EXISTS idx_reservations_idempotency ON reservations(idempotency_key);
                CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC);
            """)

    def create_sku(self, sku: str, name: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO skus (sku, name, created_at) VALUES (?, ?, ?)",
                (sku, name, datetime.utcnow().isoformat())
            )

    def get_sku(self, sku: str) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sku, name, created_at FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def adjust_stock(self, sku: str, quantity: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO stock (sku, available_quantity, reserved_quantity) VALUES (?, ?, 0) "
                "ON CONFLICT(sku) DO UPDATE SET available_quantity = available_quantity + ?",
                (sku, quantity, quantity)
            )

    def get_stock(self, sku: str) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sku, available_quantity, reserved_quantity FROM stock WHERE sku = ?",
                (sku,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str, ttl_seconds: int) -> str:
        reservation_id = str(uuid.uuid4())
        expires_at = (datetime.utcnow() + timedelta(seconds=ttl_seconds)).isoformat()
        created_at = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO reservations (id, sku, quantity, state, idempotency_key, expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (reservation_id, sku, quantity, ReservationState.PENDING.value, idempotency_key, expires_at, created_at)
            )
        return reservation_id

    def get_reservation_by_idempotency_key(self, key: str) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, sku, quantity, state, expires_at, created_at FROM reservations WHERE idempotency_key = ?",
                (key,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_reservation(self, reservation_id: str) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, sku, quantity, state, expires_at, created_at FROM reservations WHERE id = ?",
                (reservation_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_reservation_state(self, reservation_id: str, new_state: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET state = ? WHERE id = ?",
                (new_state, reservation_id)
            )

    def update_stock_reserved(self, sku: str, quantity_delta: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE stock SET reserved_quantity = reserved_quantity + ? WHERE sku = ?",
                (quantity_delta, sku)
            )

    def create_order(self, sku: str, quantity: int, state: str) -> str:
        order_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO orders (id, sku, quantity, state, created_at) VALUES (?, ?, ?, ?, ?)",
                (order_id, sku, quantity, state, created_at)
            )
        return order_id

    def get_order(self, order_id: str) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, sku, quantity, state, created_at FROM orders WHERE id = ?",
                (order_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[dict], int]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM orders")
            total = cursor.fetchone()["count"]

            offset = (page - 1) * page_size
            cursor.execute(
                "SELECT id, sku, quantity, state, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (page_size, offset)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows], total

    def update_order_state(self, order_id: str, new_state: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE orders SET state = ? WHERE id = ?",
                (new_state, order_id)
            )
