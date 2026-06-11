import sqlite3
from datetime import datetime, timezone
from typing import Optional, List, Tuple


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                available_stock INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id),
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            )
        """)

        conn.commit()
        conn.close()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_sku(self, sku: str, initial_stock: int) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "INSERT INTO skus (sku, available_stock, created_at) VALUES (?, ?, ?)",
            (sku, initial_stock, now),
        )
        conn.commit()
        sku_id = cursor.lastrowid
        conn.close()
        return sku_id

    def get_sku_by_name(self, sku: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, available_stock FROM skus WHERE sku = ?", (sku,)
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def get_sku_by_id(self, sku_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, available_stock FROM skus WHERE id = ?", (sku_id,)
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def update_stock(self, sku_id: int, amount: int) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE id = ?",
            (amount, sku_id),
        )
        conn.commit()
        cursor.execute("SELECT available_stock FROM skus WHERE id = ?", (sku_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str
    ) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """INSERT INTO reservations (sku_id, quantity, status, idempotency_key, created_at)
               VALUES (?, ?, 'PENDING', ?, ?)""",
            (sku_id, quantity, idempotency_key, now),
        )
        conn.commit()
        res_id = cursor.lastrowid
        conn.close()
        return res_id

    def get_reservation(self, res_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT r.id, r.sku_id, s.sku, r.quantity, r.status, r.created_at
               FROM reservations r
               JOIN skus s ON r.sku_id = s.id
               WHERE r.id = ?""",
            (res_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def get_reservation_by_idempotency_key(self, idempotency_key: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT r.id, r.sku_id, s.sku, r.quantity, r.status, r.created_at
               FROM reservations r
               JOIN skus s ON r.sku_id = s.id
               WHERE r.idempotency_key = ?""",
            (idempotency_key,),
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def update_reservation_status(self, res_id: int, status: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?", (status, res_id)
        )
        conn.commit()
        conn.close()

    def create_order(self, reservation_id: int, sku_id: int, quantity: int) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """INSERT INTO orders (reservation_id, sku_id, quantity, created_at)
               VALUES (?, ?, ?, ?)""",
            (reservation_id, sku_id, quantity, now),
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()
        return order_id

    def get_orders(self, page: int = 1, size: int = 10):
        conn = self.get_connection()
        cursor = conn.cursor()

        offset = (page - 1) * size

        cursor.execute(
            """SELECT o.id, s.sku, o.quantity, o.created_at
               FROM orders o
               JOIN skus s ON o.sku_id = s.id
               ORDER BY o.created_at DESC
               LIMIT ? OFFSET ?""",
            (size, offset),
        )
        rows = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) as total FROM orders")
        total_row = cursor.fetchone()
        total = total_row[0] if total_row else 0

        conn.close()
        return rows, total
