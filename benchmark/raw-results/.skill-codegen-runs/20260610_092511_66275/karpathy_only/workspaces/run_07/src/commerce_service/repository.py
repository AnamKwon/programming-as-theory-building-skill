import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Optional


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._lock = Lock()
        self._shared_conn = None
        if db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._shared_conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        conn = self._shared_conn if self._shared_conn else sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_code TEXT UNIQUE NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                idempotency_key TEXT UNIQUE NOT NULL,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending',
                reservation_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus(id),
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            )
        """)

        conn.commit()
        if not self._shared_conn:
            conn.close()

    def _get_conn(self):
        if self._shared_conn:
            return self._shared_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _close_conn(self, conn):
        if not self._shared_conn:
            conn.close()

    # SKU operations
    def create_sku(self, sku_code: str, quantity: int) -> dict:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                "INSERT INTO skus (sku_code, quantity, created_at) VALUES (?, ?, ?)",
                (sku_code, quantity, now),
            )
            conn.commit()
            sku_id = cursor.lastrowid
            self._close_conn(conn)
        return {"id": sku_id, "sku_code": sku_code, "quantity": quantity, "created_at": now}

    def get_sku(self, sku_id: int) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skus WHERE id = ?", (sku_id,))
        row = cursor.fetchone()
        self._close_conn(conn)
        return dict(row) if row else None

    def adjust_stock(self, sku_id: int, delta: int) -> Optional[dict]:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT quantity FROM skus WHERE id = ?", (sku_id,))
            row = cursor.fetchone()
            if not row:
                self._close_conn(conn)
                return None
            new_quantity = row["quantity"] + delta
            if new_quantity < 0:
                self._close_conn(conn)
                return None
            cursor.execute("UPDATE skus SET quantity = ? WHERE id = ?", (new_quantity, sku_id))
            conn.commit()
            sku = self.get_sku(sku_id)
            self._close_conn(conn)
        return sku

    # Reservation operations
    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str, expires_at: Optional[str] = None
    ) -> dict:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """
                INSERT INTO reservations (sku_id, quantity, idempotency_key, expires_at, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (sku_id, quantity, idempotency_key, expires_at, now, "pending"),
            )
            conn.commit()
            reservation_id = cursor.lastrowid
            self._close_conn(conn)
        return {
            "id": reservation_id,
            "sku_id": sku_id,
            "quantity": quantity,
            "idempotency_key": idempotency_key,
            "status": "pending",
            "expires_at": expires_at,
            "created_at": now,
        }

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
        row = cursor.fetchone()
        self._close_conn(conn)
        return dict(row) if row else None

    def get_reservation_by_key(self, idempotency_key: str) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reservations WHERE idempotency_key = ?", (idempotency_key,))
        row = cursor.fetchone()
        self._close_conn(conn)
        return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> Optional[dict]:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id),
            )
            conn.commit()
            res = self.get_reservation(reservation_id)
            self._close_conn(conn)
        return res

    # Order operations
    def create_order(
        self, sku_id: int, quantity: int, state: str = "pending", reservation_id: Optional[int] = None
    ) -> dict:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """
                INSERT INTO orders (sku_id, quantity, state, reservation_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sku_id, quantity, state, reservation_id, now),
            )
            conn.commit()
            order_id = cursor.lastrowid
            self._close_conn(conn)
        return {
            "id": order_id,
            "sku_id": sku_id,
            "quantity": quantity,
            "state": state,
            "reservation_id": reservation_id,
            "created_at": now,
        }

    def get_order(self, order_id: int) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        self._close_conn(conn)
        return dict(row) if row else None

    def update_order_state(self, order_id: int, state: str) -> Optional[dict]:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("UPDATE orders SET state = ? WHERE id = ?", (state, order_id))
            conn.commit()
            order = self.get_order(order_id)
            self._close_conn(conn)
        return order

    def list_orders(self, offset: int = 0, limit: int = 10) -> tuple[list[dict], int]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]
        cursor.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))
        rows = cursor.fetchall()
        self._close_conn(conn)
        return [dict(row) for row in rows], total

    # Cleanup
    def delete_expired_reservations(self, now: Optional[str] = None) -> int:
        if now is None:
            now = datetime.utcnow().isoformat()
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM reservations WHERE status = 'pending' AND expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            deleted = cursor.rowcount
            conn.commit()
            self._close_conn(conn)
        return deleted

    def clear_all(self):
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM orders")
            cursor.execute("DELETE FROM reservations")
            cursor.execute("DELETE FROM skus")
            conn.commit()
            self._close_conn(conn)
