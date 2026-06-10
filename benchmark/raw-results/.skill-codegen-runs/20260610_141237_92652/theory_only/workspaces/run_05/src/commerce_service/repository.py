import sqlite3
from datetime import datetime
from pathlib import Path


DB_PATH = Path(__file__).parent.parent.parent / "commerce.db"


def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skus (
            sku TEXT PRIMARY KEY,
            available_stock INT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            quantity INT NOT NULL,
            status TEXT DEFAULT 'PENDING',
            idempotency_key TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(sku) REFERENCES skus(sku)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INT NOT NULL UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(reservation_id) REFERENCES reservations(id)
        )
    """)

    conn.commit()
    conn.close()


class Repository:
    def __init__(self):
        self.db = get_db_connection()

    def close(self):
        self.db.close()

    def create_sku(self, sku: str, initial_stock: int) -> bool:
        cursor = self.db.cursor()
        try:
            cursor.execute(
                "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
                (sku, initial_stock),
            )
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_sku(self, sku: str) -> dict | None:
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def adjust_stock(self, sku: str, amount: int) -> dict | None:
        cursor = self.db.cursor()
        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
            (amount, sku),
        )
        self.db.commit()
        return self.get_sku(sku)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict | None:
        cursor = self.db.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO reservations (sku, quantity, idempotency_key, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (sku, quantity, idempotency_key, datetime.utcnow().isoformat()),
            )
            self.db.commit()
            reservation_id = cursor.lastrowid
            return self.get_reservation(reservation_id)
        except sqlite3.IntegrityError:
            return None

    def get_reservation(self, reservation_id: int) -> dict | None:
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        cursor = self.db.cursor()
        cursor.execute(
            "SELECT * FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        cursor = self.db.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id),
        )
        self.db.commit()
        return cursor.rowcount > 0

    def create_order(self, reservation_id: int) -> dict | None:
        cursor = self.db.cursor()
        try:
            cursor.execute(
                "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
                (reservation_id, datetime.utcnow().isoformat()),
            )
            self.db.commit()
            order_id = cursor.lastrowid
            return self.get_order(order_id)
        except sqlite3.IntegrityError:
            return None

    def get_order(self, order_id: int) -> dict | None:
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        cursor = self.db.cursor()
        offset = (page - 1) * size

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT * FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
            (size, offset),
        )
        rows = cursor.fetchall()
        orders = [dict(row) for row in rows]
        return orders, total
