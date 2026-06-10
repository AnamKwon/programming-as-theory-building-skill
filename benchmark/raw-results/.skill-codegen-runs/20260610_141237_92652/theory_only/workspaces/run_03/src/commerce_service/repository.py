import sqlite3
from datetime import datetime, timezone
from typing import Optional, Tuple, List


class Repository:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                initial_stock INTEGER NOT NULL,
                available_stock INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            )
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO skus (sku, initial_stock, available_stock) VALUES (?, ?, ?)",
                (sku, initial_stock, initial_stock)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def get_sku(self, sku: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def adjust_stock(self, sku: str, amount: int) -> Optional[int]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
                (amount, sku)
            )
            if cursor.rowcount == 0:
                conn.close()
                return None
            cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            conn.commit()
            return dict(row)['available_stock'] if row else None
        finally:
            conn.close()

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """INSERT INTO reservations (sku, quantity, idempotency_key, status, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (sku, quantity, idempotency_key, "PENDING", now_utc)
            )
            conn.commit()
            reservation_id = cursor.lastrowid

            cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.IntegrityError:
            conn.close()
            return None
        finally:
            conn.close()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,)
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id)
        )
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success

    def deduct_stock(self, sku: str, quantity: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE skus SET available_stock = available_stock - ? WHERE sku = ?",
            (quantity, sku)
        )
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success

    def restore_stock(self, sku: str, quantity: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
            (quantity, sku)
        )
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success

    def create_order(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        now_utc = datetime.now(timezone.utc).isoformat()
        try:
            cursor.execute(
                "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
                (reservation_id, now_utc)
            )
            conn.commit()
            order_id = cursor.lastrowid

            cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.IntegrityError:
            conn.close()
            return None
        finally:
            conn.close()

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[List[dict], int]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = dict(cursor.fetchone())['count']

        offset = (page - 1) * size
        cursor.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (size, offset)
        )
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows], total
