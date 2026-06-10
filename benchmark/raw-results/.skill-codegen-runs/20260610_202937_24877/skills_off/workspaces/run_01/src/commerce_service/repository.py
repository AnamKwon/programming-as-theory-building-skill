import sqlite3
from datetime import datetime
from pathlib import Path


class Database:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self.conn = None
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
        return self.conn

    def init_db(self):
        conn = self.get_connection()
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
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                idempotency_key TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus(id)
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

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None


class SKURepository:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
            (sku, initial_stock),
        )
        conn.commit()
        sku_id = cursor.lastrowid
        return self.get_sku_by_id(sku_id)

    def get_sku_by_sku(self, sku: str) -> dict | None:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_sku_by_id(self, sku_id: int) -> dict | None:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skus WHERE id = ?", (sku_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_stock(self, sku_id: int, amount: int) -> dict:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE id = ?",
            (amount, sku_id),
        )
        conn.commit()
        return self.get_sku_by_id(sku_id)


class ReservationRepository:
    def __init__(self, db: Database):
        self.db = db

    def create_reservation(
        self,
        sku_id: int,
        sku: str,
        quantity: int,
        idempotency_key: str,
        created_at: str,
    ) -> dict:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO reservations
            (sku_id, sku, quantity, status, idempotency_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (sku_id, sku, quantity, "PENDING", idempotency_key, created_at),
        )
        conn.commit()
        reservation_id = cursor.lastrowid
        return self.get_reservation_by_id(reservation_id)

    def get_reservation_by_id(self, reservation_id: int) -> dict | None:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM reservations WHERE idempotency_key = ?", (idempotency_key,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> dict | None:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id),
        )
        conn.commit()
        return self.get_reservation_by_id(reservation_id)


class OrderRepository:
    def __init__(self, db: Database):
        self.db = db

    def create_order(self, reservation_id: int, created_at: str) -> dict:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
            (reservation_id, created_at),
        )
        conn.commit()
        order_id = cursor.lastrowid
        return self.get_order_by_id(order_id)

    def get_order_by_id(self, order_id: int) -> dict | None:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_orders(self, page: int, size: int) -> tuple[list[dict], int]:
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]

        offset = (page - 1) * size
        cursor.execute(
            "SELECT * FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
            (size, offset),
        )
        rows = cursor.fetchall()
        orders = [dict(row) for row in rows]
        return orders, total
