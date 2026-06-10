import sqlite3
import threading
from datetime import datetime
from pathlib import Path


class Repository:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._thread_local = threading.local()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._thread_local, "connection"):
            self._thread_local.connection = sqlite3.connect(self.db_path)
            self._thread_local.connection.row_factory = sqlite3.Row
        return self._thread_local.connection

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                sku TEXT PRIMARY KEY,
                available_stock INTEGER NOT NULL,
                reserved_stock INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY(sku) REFERENCES skus(sku)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_from_reservation_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(sku) REFERENCES skus(sku),
                FOREIGN KEY(created_from_reservation_id) REFERENCES reservations(id)
            )
        """)

        conn.commit()

    def create_sku(self, sku: str, initial_stock: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO skus (sku, available_stock, reserved_stock, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (sku, initial_stock, 0, datetime.utcnow().isoformat()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_sku(self, sku: str) -> dict | None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def adjust_stock(self, sku: str, amount: int) -> dict | None:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE skus
            SET available_stock = available_stock + ?
            WHERE sku = ?
            """,
            (amount, sku),
        )
        conn.commit()

        if cursor.rowcount == 0:
            return None

        return self.get_sku(sku)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict | None:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO reservations (sku, quantity, status, idempotency_key, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sku, quantity, "PENDING", idempotency_key, datetime.utcnow().isoformat()),
        )
        conn.commit()

        cursor.execute("SELECT * FROM reservations WHERE id = ?", (cursor.lastrowid,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_reservation(self, reservation_id: int) -> dict | None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> dict | None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id),
        )
        conn.commit()

        if cursor.rowcount == 0:
            return None

        return self.get_reservation(reservation_id)

    def deduct_stock_for_reservation(self, sku: str, quantity: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE skus
            SET available_stock = available_stock - ?,
                reserved_stock = reserved_stock + ?
            WHERE sku = ? AND available_stock >= ?
            """,
            (quantity, quantity, sku, quantity),
        )
        conn.commit()
        return cursor.rowcount > 0

    def restore_stock_from_reservation(self, sku: str, quantity: int) -> dict | None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE skus
            SET available_stock = available_stock + ?,
                reserved_stock = reserved_stock - ?
            WHERE sku = ?
            """,
            (quantity, quantity, sku),
        )
        conn.commit()

        if cursor.rowcount == 0:
            return None

        return self.get_sku(sku)

    def create_order(self, sku: str, quantity: int, reservation_id: int) -> dict | None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO orders (sku, quantity, status, created_from_reservation_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sku, quantity, "CONFIRMED", reservation_id, datetime.utcnow().isoformat()),
        )
        conn.commit()

        cursor.execute("SELECT * FROM orders WHERE id = ?", (cursor.lastrowid,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]

        offset = (page - 1) * size
        cursor.execute(
            """
            SELECT * FROM orders
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (size, offset),
        )

        rows = cursor.fetchall()
        orders = [dict(row) for row in rows]
        return orders, total
