import sqlite3
import os
from datetime import datetime, timezone
from typing import Optional, List, Tuple


class Database:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                sku TEXT PRIMARY KEY,
                available_stock INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                confirmed_at TEXT,
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL UNIQUE,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id),
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            "INSERT INTO skus (sku, available_stock, created_at) VALUES (?, ?, ?)",
            (sku, initial_stock, now),
        )
        conn.commit()
        conn.close()

        return {"sku": sku, "available_stock": initial_stock}

    def get_sku(self, sku: str) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT sku, available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {"sku": row["sku"], "available_stock": row["available_stock"]}
        return None

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
            (amount, sku),
        )
        conn.commit()

        cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {"sku": sku, "available_stock": row["available_stock"]}
        return None

    def get_sku_stock(self, sku: str) -> Optional[int]:
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return row["available_stock"]
        return None

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """
            INSERT INTO reservations (sku, quantity, idempotency_key, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sku, quantity, idempotency_key, "PENDING", now),
        )
        conn.commit()
        reservation_id = cursor.lastrowid
        conn.close()

        return {
            "id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "status": "PENDING",
            "created_at": now,
        }

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, sku, quantity, status, created_at
            FROM reservations WHERE idempotency_key = ?
            """,
            (key,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "id": row["id"],
                "sku": row["sku"],
                "quantity": row["quantity"],
                "status": row["status"],
                "created_at": row["created_at"],
            }
        return None

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, sku, quantity, status, created_at, confirmed_at
            FROM reservations WHERE id = ?
            """,
            (reservation_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "id": row["id"],
                "sku": row["sku"],
                "quantity": row["quantity"],
                "status": row["status"],
                "created_at": row["created_at"],
                "confirmed_at": row["confirmed_at"],
            }
        return None

    def update_reservation_status(
        self, reservation_id: int, status: str, confirmed_at: Optional[str] = None
    ) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()

        if confirmed_at:
            cursor.execute(
                """
                UPDATE reservations SET status = ?, confirmed_at = ? WHERE id = ?
                """,
                (status, confirmed_at, reservation_id),
            )
        else:
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id),
            )

        conn.commit()
        conn.close()
        return True

    def create_order(
        self, reservation_id: int, sku: str, quantity: int
    ) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """
            INSERT INTO orders (reservation_id, sku, quantity, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (reservation_id, sku, quantity, now),
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()

        return {
            "id": order_id,
            "reservation_id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "created_at": now,
        }

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[List[dict], int]:
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as total FROM orders")
        total = cursor.fetchone()["total"]

        offset = (page - 1) * size
        cursor.execute(
            """
            SELECT id, reservation_id, sku, quantity, created_at
            FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?
            """,
            (size, offset),
        )
        rows = cursor.fetchall()
        conn.close()

        orders = [
            {
                "id": row["id"],
                "reservation_id": row["reservation_id"],
                "sku": row["sku"],
                "quantity": row["quantity"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

        return orders, total

    def clear_all(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM orders")
        cursor.execute("DELETE FROM reservations")
        cursor.execute("DELETE FROM skus")
        conn.commit()
        conn.close()
