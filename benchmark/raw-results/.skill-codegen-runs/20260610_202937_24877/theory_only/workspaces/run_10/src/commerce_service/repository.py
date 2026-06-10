import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

DATABASE_PATH = Path("commerce.db")


class Repository:
    def __init__(self, db_path: Path = DATABASE_PATH):
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
                sku TEXT PRIMARY KEY,
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
                updated_at TEXT NOT NULL,
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
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            "INSERT INTO skus (sku, available_stock, created_at) VALUES (?, ?, ?)",
            (sku, initial_stock, now),
        )
        conn.commit()
        conn.close()

        return {
            "sku": sku,
            "available_stock": initial_stock,
            "created_at": now,
        }

    def get_sku(self, sku: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT sku, available_stock, created_at FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        new_stock = row[0] + amount
        cursor.execute("UPDATE skus SET available_stock = ? WHERE sku = ?", (new_stock, sku))
        conn.commit()
        conn.close()

        return {"sku": sku, "available_stock": new_stock}

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """INSERT INTO reservations
               (sku, quantity, status, idempotency_key, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sku, quantity, "PENDING", idempotency_key, now, now),
        )
        conn.commit()
        reservation_id = cursor.lastrowid
        conn.close()

        return {
            "id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "status": "PENDING",
            "idempotency_key": idempotency_key,
            "created_at": now,
        }

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, sku, quantity, status, idempotency_key, created_at, updated_at
               FROM reservations WHERE id = ?""",
            (reservation_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, sku, quantity, status, idempotency_key, created_at, updated_at
               FROM reservations WHERE idempotency_key = ?""",
            (idempotency_key,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def update_reservation_status(self, reservation_id: int, status: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """UPDATE reservations SET status = ?, updated_at = ? WHERE id = ?""",
            (status, now, reservation_id),
        )
        conn.commit()

        cursor.execute(
            """SELECT id, sku, quantity, status, idempotency_key, created_at, updated_at
               FROM reservations WHERE id = ?""",
            (reservation_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def create_order(self, reservation_id: int, sku: str, quantity: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """INSERT INTO orders (reservation_id, sku, quantity, created_at)
               VALUES (?, ?, ?, ?)""",
            (reservation_id, sku, quantity, now),
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()

        return {
            "id": order_id,
            "reservation_id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "created_at": now,
        }

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[list, int]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM orders")
        total = cursor.fetchone()[0]

        offset = (page - 1) * size
        cursor.execute(
            """SELECT id, reservation_id, sku, quantity, created_at FROM orders
               ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (size, offset),
        )
        rows = cursor.fetchall()
        conn.close()

        orders = [dict(row) for row in rows]
        return orders, total
