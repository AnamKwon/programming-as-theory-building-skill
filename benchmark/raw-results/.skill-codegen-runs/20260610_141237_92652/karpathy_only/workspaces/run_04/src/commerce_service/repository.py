import sqlite3
import threading
from typing import Optional, List, Tuple
from pathlib import Path


class Repository:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._connection = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sku (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                available_stock INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                FOREIGN KEY (sku) REFERENCES sku(sku)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS "order" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL UNIQUE,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservation(id),
                FOREIGN KEY (sku) REFERENCES sku(sku)
            )
        """)

        conn.commit()

    def create_sku(self, sku: str, initial_stock: int) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sku (sku, available_stock) VALUES (?, ?)",
            (sku, initial_stock)
        )
        conn.commit()
        return cursor.lastrowid

    def get_sku_stock(self, sku: str) -> Optional[int]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT available_stock FROM sku WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        return row[0] if row else None

    def adjust_stock(self, sku: str, amount: int) -> Optional[int]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sku SET available_stock = available_stock + ? WHERE sku = ?",
            (amount, sku)
        )
        conn.commit()

        if cursor.rowcount == 0:
            return None

        cursor.execute("SELECT available_stock FROM sku WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        return row[0] if row else None

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str, created_at: float) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO reservation (sku, quantity, status, created_at, idempotency_key)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sku, quantity, "PENDING", created_at, idempotency_key)
        )
        conn.commit()
        return cursor.lastrowid

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, status, created_at, idempotency_key FROM reservation WHERE idempotency_key = ?",
            (idempotency_key,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "sku": row[1],
                "quantity": row[2],
                "status": row[3],
                "created_at": row[4],
                "idempotency_key": row[5]
            }
        return None

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, status, created_at, idempotency_key FROM reservation WHERE id = ?",
            (reservation_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "sku": row[1],
                "quantity": row[2],
                "status": row[3],
                "created_at": row[4],
                "idempotency_key": row[5]
            }
        return None

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservation SET status = ? WHERE id = ?",
            (status, reservation_id)
        )
        conn.commit()
        return cursor.rowcount > 0

    def create_order(self, reservation_id: int, sku: str, quantity: int, created_at: float) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO "order" (reservation_id, sku, quantity, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (reservation_id, sku, quantity, created_at)
        )
        conn.commit()
        return cursor.lastrowid

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[List[dict], int]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM \"order\"")
        total = cursor.fetchone()[0]

        offset = (page - 1) * size
        cursor.execute(
            """
            SELECT id, reservation_id, sku, quantity, created_at
            FROM "order"
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (size, offset)
        )
        rows = cursor.fetchall()

        orders = []
        for row in rows:
            orders.append({
                "id": row[0],
                "reservation_id": row[1],
                "sku": row[2],
                "quantity": row[3],
                "created_at": row[4]
            })

        return orders, total

    def sku_exists(self, sku: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM sku WHERE sku = ?", (sku,))
        return cursor.fetchone() is not None

    def get_order_by_reservation_id(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, reservation_id, sku, quantity, created_at
            FROM "order"
            WHERE reservation_id = ?
            """,
            (reservation_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "reservation_id": row[1],
                "sku": row[2],
                "quantity": row[3],
                "created_at": row[4]
            }
        return None
