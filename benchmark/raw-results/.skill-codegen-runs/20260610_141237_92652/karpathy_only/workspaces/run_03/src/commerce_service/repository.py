import sqlite3
from datetime import datetime
from typing import Optional
from pathlib import Path


class Repository:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._connection = None
        if db_path == ":memory:":
            self._connection = sqlite3.connect(":memory:", check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is not None:
            return self._connection
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _close_connection(self, conn: sqlite3.Connection) -> None:
        if self.db_path != ":memory:":
            conn.close()

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sku (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                available_stock INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS "order" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY(reservation_id) REFERENCES reservation(id)
            )
        """)

        conn.commit()
        self._close_connection(conn)

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            "INSERT INTO sku (sku, available_stock, created_at) VALUES (?, ?, ?)",
            (sku, initial_stock, now)
        )
        conn.commit()

        sku_id = cursor.lastrowid
        self._close_connection(conn)

        return {
            "id": sku_id,
            "sku": sku,
            "available_stock": initial_stock,
            "created_at": now
        }

    def get_sku_by_name(self, sku: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, sku, available_stock, created_at FROM sku WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        self._close_connection(conn)

        if row:
            return dict(row)
        return None

    def adjust_stock(self, sku: str, amount: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT available_stock FROM sku WHERE sku = ?", (sku,))
        row = cursor.fetchone()

        if not row:
            self._close_connection(conn)
            raise ValueError(f"SKU {sku} not found")

        new_stock = row["available_stock"] + amount
        cursor.execute("UPDATE sku SET available_stock = ? WHERE sku = ?", (new_stock, sku))
        conn.commit()
        self._close_connection(conn)

        return {"sku": sku, "available_stock": new_stock}

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, sku, quantity, status, created_at FROM reservation WHERE idempotency_key = ?",
            (idempotency_key,)
        )
        row = cursor.fetchone()
        self._close_connection(conn)

        if row:
            return dict(row)
        return None

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str, status: str = "PENDING"
    ) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            "INSERT INTO reservation (sku, quantity, idempotency_key, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (sku, quantity, idempotency_key, status, now)
        )
        conn.commit()

        reservation_id = cursor.lastrowid
        self._close_connection(conn)

        return {
            "id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "status": status,
            "created_at": now
        }

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, sku, quantity, status, created_at FROM reservation WHERE id = ?",
            (reservation_id,)
        )
        row = cursor.fetchone()
        self._close_connection(conn)

        if row:
            return dict(row)
        return None

    def update_reservation_status(self, reservation_id: int, status: str) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE reservation SET status = ? WHERE id = ?",
            (status, reservation_id)
        )
        conn.commit()
        self._close_connection(conn)

    def create_order(self, reservation_id: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            "INSERT INTO \"order\" (reservation_id, created_at) VALUES (?, ?)",
            (reservation_id, now)
        )
        conn.commit()

        order_id = cursor.lastrowid
        self._close_connection(conn)

        return {
            "id": order_id,
            "reservation_id": reservation_id,
            "created_at": now
        }

    def list_orders(self, offset: int = 0, limit: int = 10) -> tuple[list[dict], int]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM \"order\"")
        total = cursor.fetchone()[0]

        cursor.execute(
            "SELECT id, reservation_id, created_at FROM \"order\" ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        rows = cursor.fetchall()
        self._close_connection(conn)

        orders = [dict(row) for row in rows]
        return orders, total
