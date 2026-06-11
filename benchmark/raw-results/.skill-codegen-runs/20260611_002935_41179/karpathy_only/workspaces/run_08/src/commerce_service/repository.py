import sqlite3
from datetime import datetime
from typing import Optional


DB_PATH = ":memory:"


class Repository:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skus (
                sku TEXT PRIMARY KEY,
                available_stock INTEGER NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            )
            """
        )
        self.conn.commit()

    def create_sku(self, sku: str, initial_stock: int) -> bool:
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
                (sku, initial_stock),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_sku_stock(self, sku: str) -> Optional[int]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        return row[0] if row else None

    def adjust_stock(self, sku: str, amount: int) -> Optional[int]:
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
            (amount, sku),
        )
        if cursor.rowcount == 0:
            return None
        cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        self.conn.commit()
        return row[0] if row else None

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Optional[dict]:
        try:
            cursor = self.conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """
                INSERT INTO reservations (sku, quantity, idempotency_key, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sku, quantity, idempotency_key, "PENDING", now),
            )
            reservation_id = cursor.lastrowid
            self.conn.commit()
            return {
                "id": reservation_id,
                "sku": sku,
                "quantity": quantity,
                "idempotency_key": idempotency_key,
                "status": "PENDING",
                "created_at": now,
            }
        except sqlite3.IntegrityError:
            return None

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, idempotency_key, status, created_at FROM reservations WHERE id = ?",
            (reservation_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "sku": row[1],
            "quantity": row[2],
            "idempotency_key": row[3],
            "status": row[4],
            "created_at": row[5],
        }

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, idempotency_key, status, created_at FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "sku": row[1],
            "quantity": row[2],
            "idempotency_key": row[3],
            "status": row[4],
            "created_at": row[5],
        }

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id),
        )
        result = cursor.rowcount > 0
        self.conn.commit()
        return result

    def create_order(self, reservation_id: int) -> Optional[dict]:
        try:
            cursor = self.conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
                (reservation_id, now),
            )
            order_id = cursor.lastrowid
            self.conn.commit()
            return {
                "id": order_id,
                "reservation_id": reservation_id,
                "created_at": now,
            }
        except sqlite3.IntegrityError:
            return None

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orders")
        total = cursor.fetchone()[0]
        offset = (page - 1) * size
        cursor.execute(
            "SELECT id, reservation_id, created_at FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
            (size, offset),
        )
        rows = cursor.fetchall()
        orders = [
            {
                "id": row[0],
                "reservation_id": row[1],
                "created_at": row[2],
            }
            for row in rows
        ]
        return orders, total
