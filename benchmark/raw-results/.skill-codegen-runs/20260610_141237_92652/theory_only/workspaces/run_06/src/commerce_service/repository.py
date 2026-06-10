import sqlite3
from datetime import datetime
from typing import Optional


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                sku TEXT PRIMARY KEY,
                stock INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                idempotency_key TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                reservation_id INTEGER NOT NULL UNIQUE,
                FOREIGN KEY (sku) REFERENCES skus(sku),
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            )
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO skus (sku, stock) VALUES (?, ?)", (sku, initial_stock))
        conn.commit()
        conn.close()

    def get_sku_stock(self, sku: str) -> Optional[int]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()
        return row["stock"] if row else None

    def adjust_stock(self, sku: str, amount: int) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE skus SET stock = stock + ? WHERE sku = ?", (amount, sku))
        conn.commit()
        cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()
        return row["stock"] if row else 0

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute(
            "INSERT INTO reservations (sku, quantity, status, idempotency_key, created_at) VALUES (?, ?, 'PENDING', ?, ?)",
            (sku, quantity, idempotency_key, now),
        )
        conn.commit()
        reservation_id = cursor.lastrowid
        conn.close()
        return reservation_id

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, status, idempotency_key, created_at FROM reservations WHERE id = ?",
            (reservation_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, status, idempotency_key, created_at FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE reservations SET status = ? WHERE id = ?", (status, reservation_id))
        conn.commit()
        conn.close()

    def create_order(self, sku: str, quantity: int, reservation_id: int) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute(
            "INSERT INTO orders (sku, quantity, created_at, reservation_id) VALUES (?, ?, ?, ?)",
            (sku, quantity, now, reservation_id),
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()
        return order_id

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]

        offset = (page - 1) * size
        cursor.execute(
            "SELECT id, sku, quantity, created_at, reservation_id FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (size, offset),
        )
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows], total
