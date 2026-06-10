import sqlite3
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path


class Repository:
    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        self._is_memory = self.db_path == ":memory:"
        self._persistent_conn = None
        if self._is_memory:
            self._persistent_conn = sqlite3.connect(
                self.db_path, check_same_thread=False
            )
            self._persistent_conn.row_factory = sqlite3.Row
            self._persistent_conn.execute("PRAGMA foreign_keys = ON")
        self._init_db()

    @contextmanager
    def _get_connection(self):
        if self._persistent_conn:
            conn = self._persistent_conn
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if not self._persistent_conn:
                conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stock (
                    sku_id INTEGER PRIMARY KEY,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus (id)
                );

                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus (id)
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reservation_id INTEGER NOT NULL,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (reservation_id) REFERENCES reservations (id),
                    FOREIGN KEY (sku_id) REFERENCES skus (id)
                );

                CREATE INDEX IF NOT EXISTS idx_reservations_idempotency_key
                    ON reservations (idempotency_key);
                CREATE INDEX IF NOT EXISTS idx_reservations_expires_at
                    ON reservations (expires_at);
                CREATE INDEX IF NOT EXISTS idx_orders_created_at
                    ON orders (created_at DESC);
            """)

    def create_sku(self, name: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO skus (name, created_at) VALUES (?, ?)",
                (name, datetime.utcnow().isoformat()),
            )
            return cursor.lastrowid

    def get_sku(self, sku_id: int) -> dict | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, name, created_at FROM skus WHERE id = ?", (sku_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_stock(self, sku_id: int) -> dict | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT sku_id, quantity, updated_at FROM stock WHERE sku_id = ?",
                (sku_id,),
            ).fetchone()
            return dict(row) if row else None

    def adjust_stock(self, sku_id: int, delta: int) -> dict:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO stock (sku_id, quantity, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT(sku_id) DO UPDATE SET quantity = quantity + ?, updated_at = ?",
                (sku_id, delta, datetime.utcnow().isoformat(), delta, datetime.utcnow().isoformat()),
            )
            row = conn.execute(
                "SELECT sku_id, quantity, updated_at FROM stock WHERE sku_id = ?",
                (sku_id,),
            ).fetchone()
            return dict(row)

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str, expires_at: str
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO reservations (sku_id, quantity, status, idempotency_key, created_at, expires_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    sku_id,
                    quantity,
                    "reserved",
                    idempotency_key,
                    datetime.utcnow().isoformat(),
                    expires_at,
                ),
            )
            return cursor.lastrowid

    def get_reservation(self, reservation_id: int) -> dict | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, sku_id, quantity, status, idempotency_key, created_at, expires_at"
                " FROM reservations WHERE id = ?",
                (reservation_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, sku_id, quantity, status, idempotency_key, created_at, expires_at"
                " FROM reservations WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> dict:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id),
            )
            row = conn.execute(
                "SELECT id, sku_id, quantity, status, idempotency_key, created_at, expires_at"
                " FROM reservations WHERE id = ?",
                (reservation_id,),
            ).fetchone()
            return dict(row)

    def create_order(
        self, reservation_id: int, sku_id: int, quantity: int
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO orders (reservation_id, sku_id, quantity, status, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (reservation_id, sku_id, quantity, "completed", datetime.utcnow().isoformat()),
            )
            return cursor.lastrowid

    def get_order(self, order_id: int) -> dict | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, reservation_id, sku_id, quantity, status, created_at"
                " FROM orders WHERE id = ?",
                (order_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_orders(self, limit: int = 20, cursor: int = 0) -> tuple[list[dict], int | None]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, reservation_id, sku_id, quantity, status, created_at"
                " FROM orders WHERE id > ? ORDER BY created_at DESC LIMIT ?",
                (cursor, limit + 1),
            ).fetchall()
            orders = [dict(row) for row in rows[:limit]]
            next_cursor = rows[limit]["id"] if len(rows) > limit else None
            return orders, next_cursor
