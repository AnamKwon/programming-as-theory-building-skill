import sqlite3
from datetime import datetime
from typing import Optional, Tuple
import uuid


DATABASE_URL = ":memory:"


class Repository:
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_url)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                sku TEXT PRIMARY KEY,
                available_stock INTEGER NOT NULL,
                reserved_stock INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id TEXT PRIMARY KEY,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                reservation_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku) REFERENCES skus(sku),
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            )
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.utcnow().isoformat()
        cursor.execute(
            """
            INSERT INTO skus (sku, available_stock, reserved_stock, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (sku, initial_stock, 0, now),
        )
        conn.commit()
        conn.close()

        return {"sku": sku, "available_stock": initial_stock, "reserved_stock": 0}

    def get_sku(self, sku: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT sku, available_stock, reserved_stock FROM skus WHERE sku = ?",
            (sku,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "sku": row["sku"],
                "available_stock": row["available_stock"],
                "reserved_stock": row["reserved_stock"],
            }
        return None

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return None

        new_stock = row["available_stock"] + amount
        cursor.execute(
            "UPDATE skus SET available_stock = ? WHERE sku = ?",
            (new_stock, sku),
        )
        conn.commit()
        conn.close()

        return {"sku": sku, "available_stock": new_stock}

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()

        reservation_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        cursor.execute(
            """
            INSERT INTO reservations (id, sku, quantity, status, idempotency_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (reservation_id, sku, quantity, "PENDING", idempotency_key, now),
        )

        cursor.execute(
            """
            UPDATE skus SET available_stock = available_stock - ?,
                           reserved_stock = reserved_stock + ?
            WHERE sku = ?
            """,
            (quantity, quantity, sku),
        )

        conn.commit()
        conn.close()

        return {
            "id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "status": "PENDING",
            "created_at": now,
            "idempotency_key": idempotency_key,
        }

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, sku, quantity, status, created_at, idempotency_key
            FROM reservations WHERE idempotency_key = ?
            """,
            (idempotency_key,),
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
                "idempotency_key": row["idempotency_key"],
            }
        return None

    def get_reservation(self, reservation_id: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, sku, quantity, status, created_at, idempotency_key
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
                "idempotency_key": row["idempotency_key"],
            }
        return None

    def update_reservation_status(self, reservation_id: str, status: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id),
        )
        conn.commit()
        conn.close()

        return cursor.rowcount > 0

    def create_order(
        self, reservation_id: str, sku: str, quantity: int
    ) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()

        order_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        cursor.execute(
            """
            INSERT INTO orders (id, reservation_id, sku, quantity, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (order_id, reservation_id, sku, quantity, "CONFIRMED", now),
        )

        cursor.execute(
            """
            UPDATE skus SET reserved_stock = reserved_stock - ?
            WHERE sku = ?
            """,
            (quantity, sku),
        )

        conn.commit()
        conn.close()

        return {
            "id": order_id,
            "sku": sku,
            "quantity": quantity,
            "status": "CONFIRMED",
            "created_at": now,
        }

    def restore_stock(self, sku: str, quantity: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE skus SET available_stock = available_stock + ?,
                           reserved_stock = reserved_stock - ?
            WHERE sku = ?
            """,
            (quantity, quantity, sku),
        )
        conn.commit()
        conn.close()

        return cursor.rowcount > 0

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[list, int]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]

        offset = (page - 1) * size
        cursor.execute(
            """
            SELECT id, sku, quantity, status, created_at
            FROM orders
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (size, offset),
        )
        rows = cursor.fetchall()
        conn.close()

        orders = [
            {
                "id": row["id"],
                "sku": row["sku"],
                "quantity": row["quantity"],
                "status": row["status"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

        return orders, total
