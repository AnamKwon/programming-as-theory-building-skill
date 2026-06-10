import sqlite3
from datetime import datetime
from typing import Optional


class SQLiteRepository:
    def __init__(self, db_path: str = "commerce.db"):
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
                available_stock INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            )
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
            (sku, initial_stock),
        )
        conn.commit()
        sku_id = cursor.lastrowid
        conn.close()
        return {"id": sku_id, "sku": sku, "available_stock": initial_stock}

    def get_sku_by_name(self, sku: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, sku, available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_sku_by_id(self, sku_id: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, sku, available_stock FROM skus WHERE id = ?", (sku_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def adjust_stock(self, sku_id: int, amount: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE id = ?",
            (amount, sku_id),
        )
        conn.commit()
        cursor.execute("SELECT sku, available_stock FROM skus WHERE id = ?", (sku_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str
    ) -> dict:
        now = datetime.utcnow()
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO reservations (sku_id, quantity, status, idempotency_key, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (sku_id, quantity, "PENDING", idempotency_key, now, now),
        )
        conn.commit()
        reservation_id = cursor.lastrowid
        conn.close()
        return {
            "id": reservation_id,
            "sku_id": sku_id,
            "quantity": quantity,
            "status": "PENDING",
            "idempotency_key": idempotency_key,
            "created_at": now,
            "updated_at": now,
        }

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT r.id, r.sku_id, s.sku, r.quantity, r.status, r.idempotency_key, r.created_at, r.updated_at
            FROM reservations r
            JOIN skus s ON r.sku_id = s.id
            WHERE r.idempotency_key = ?
            """,
            (key,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_reservation_by_id(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT r.id, r.sku_id, s.sku, r.quantity, r.status, r.idempotency_key, r.created_at, r.updated_at
            FROM reservations r
            JOIN skus s ON r.sku_id = s.id
            WHERE r.id = ?
            """,
            (reservation_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> Optional[dict]:
        now = datetime.utcnow()
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, reservation_id),
        )
        conn.commit()
        cursor.execute(
            """
            SELECT r.id, r.sku_id, s.sku, r.quantity, r.status, r.idempotency_key, r.created_at, r.updated_at
            FROM reservations r
            JOIN skus s ON r.sku_id = s.id
            WHERE r.id = ?
            """,
            (reservation_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def create_order(self, reservation_id: int) -> dict:
        now = datetime.utcnow()
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
            (reservation_id, now),
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()
        return {"id": order_id, "reservation_id": reservation_id, "created_at": now}

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        offset = (page - 1) * size
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as total FROM orders")
        total = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT id, reservation_id, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (size, offset),
        )
        rows = cursor.fetchall()
        conn.close()

        orders = [dict(row) for row in rows]
        return orders, total

    def get_order_by_reservation_id(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, reservation_id, created_at FROM orders WHERE reservation_id = ?",
            (reservation_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
