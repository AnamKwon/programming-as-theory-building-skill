import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


class Database:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        cursor = self.conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                available_stock INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku) REFERENCES skus(sku)
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            );
        """)
        self.conn.commit()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
            (sku, initial_stock)
        )
        self.conn.commit()
        return {"sku": sku, "available_stock": initial_stock}

    def get_sku(self, sku: str) -> Optional[dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def update_sku_stock(self, sku: str, amount: int) -> dict:
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
            (amount, sku)
        )
        self.conn.commit()
        cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        return {"sku": sku, "available_stock": row[0]}

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str,
        created_at: datetime
    ) -> dict:
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO reservations (sku, quantity, idempotency_key, status, created_at)
               VALUES (?, ?, ?, 'PENDING', ?)""",
            (sku, quantity, idempotency_key, created_at.isoformat())
        )
        self.conn.commit()
        cursor.execute(
            "SELECT id FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,)
        )
        res_id = cursor.fetchone()[0]
        return {
            "id": res_id,
            "sku": sku,
            "quantity": quantity,
            "idempotency_key": idempotency_key,
            "status": "PENDING",
            "created_at": created_at
        }

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
        row = cursor.fetchone()
        if row:
            data = dict(row)
            data["created_at"] = datetime.fromisoformat(data["created_at"])
            return data
        return None

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM reservations WHERE idempotency_key = ?",
            (key,)
        )
        row = cursor.fetchone()
        if row:
            data = dict(row)
            data["created_at"] = datetime.fromisoformat(data["created_at"])
            return data
        return None

    def update_reservation_status(self, reservation_id: int, status: str) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id)
        )
        self.conn.commit()

    def create_order(self, reservation_id: int, created_at: datetime) -> dict:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
            (reservation_id, created_at.isoformat())
        )
        self.conn.commit()
        cursor.execute(
            "SELECT id FROM orders WHERE reservation_id = ?",
            (reservation_id,)
        )
        order_id = cursor.fetchone()[0]
        return {
            "id": order_id,
            "reservation_id": reservation_id,
            "created_at": created_at
        }

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orders")
        total = cursor.fetchone()[0]

        offset = (page - 1) * size
        cursor.execute(
            "SELECT * FROM orders ORDER BY id LIMIT ? OFFSET ?",
            (size, offset)
        )
        rows = cursor.fetchall()
        orders = []
        for row in rows:
            data = dict(row)
            data["created_at"] = datetime.fromisoformat(data["created_at"])
            orders.append(data)
        return orders, total

    def close(self):
        self.conn.close()
