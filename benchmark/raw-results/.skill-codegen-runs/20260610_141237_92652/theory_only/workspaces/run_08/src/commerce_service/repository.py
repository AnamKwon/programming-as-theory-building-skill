import sqlite3
from datetime import datetime
from typing import Optional, Tuple, List


class Repository:
    def __init__(self, db_path: str = ":memory:"):
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
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TEXT NOT NULL,
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
            (sku, initial_stock)
        )
        conn.commit()
        sku_id = cursor.lastrowid
        conn.close()
        return {"id": sku_id, "sku": sku, "available_stock": initial_stock}

    def get_sku_by_sku(self, sku: str) -> Optional[dict]:
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

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        new_stock = row["available_stock"] + amount
        cursor.execute(
            "UPDATE skus SET available_stock = ? WHERE sku = ?",
            (new_stock, sku)
        )
        conn.commit()
        conn.close()
        return {"sku": sku, "available_stock": new_stock}

    def create_reservation(self, sku_id: int, sku: str, quantity: int, idempotency_key: str) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            """INSERT INTO reservations (sku_id, sku, quantity, status, created_at, idempotency_key)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sku_id, sku, quantity, "PENDING", now, idempotency_key)
        )
        conn.commit()
        reservation_id = cursor.lastrowid
        conn.close()

        return {
            "id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "status": "PENDING",
            "created_at": datetime.fromisoformat(now),
            "idempotency_key": idempotency_key,
        }

    def get_reservation_by_id(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku_id, sku, quantity, status, created_at, idempotency_key FROM reservations WHERE id = ?",
            (reservation_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        data = dict(row)
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return data

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku_id, sku, quantity, status, created_at, idempotency_key FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        data = dict(row)
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return data

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id)
        )
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success

    def create_order(self, reservation_id: int, sku: str, quantity: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            "INSERT INTO orders (reservation_id, sku, quantity, created_at) VALUES (?, ?, ?, ?)",
            (reservation_id, sku, quantity, now)
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()

        return {
            "id": order_id,
            "reservation_id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "created_at": datetime.fromisoformat(now),
        }

    def get_orders(self, page: int, size: int) -> Tuple[List[dict], int]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]

        offset = (page - 1) * size
        cursor.execute(
            "SELECT id, reservation_id, sku, quantity, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (size, offset)
        )
        rows = cursor.fetchall()
        conn.close()

        orders = []
        for row in rows:
            data = dict(row)
            data["created_at"] = datetime.fromisoformat(data["created_at"])
            orders.append(data)

        return orders, total
