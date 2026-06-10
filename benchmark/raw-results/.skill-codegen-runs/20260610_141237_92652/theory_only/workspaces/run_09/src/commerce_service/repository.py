import sqlite3
from datetime import datetime
from typing import Optional, Tuple


class Repository:
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
                id INTEGER PRIMARY KEY,
                sku TEXT UNIQUE NOT NULL,
                stock INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY,
                reservation_id INTEGER NOT NULL UNIQUE,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id),
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO skus (sku, stock) VALUES (?, ?)",
                (sku, initial_stock),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_sku_stock(self, sku: str) -> Optional[int]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def adjust_stock(self, sku: str, amount: int) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE skus SET stock = stock + ? WHERE sku = ?",
                (amount, sku),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"SKU {sku} not found")
            conn.commit()

            cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return row[0]
        finally:
            conn.close()

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO reservations (sku, quantity, status, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (sku, quantity, "PENDING", idempotency_key, datetime.utcnow()),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """SELECT id, sku, quantity, status, idempotency_key, created_at
                   FROM reservations WHERE id = ?""",
                (reservation_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "sku": row[1],
                    "quantity": row[2],
                    "status": row[3],
                    "idempotency_key": row[4],
                    "created_at": datetime.fromisoformat(row[5]),
                }
            return None
        finally:
            conn.close()

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """SELECT id, sku, quantity, status, idempotency_key, created_at
                   FROM reservations WHERE idempotency_key = ?""",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "sku": row[1],
                    "quantity": row[2],
                    "status": row[3],
                    "idempotency_key": row[4],
                    "created_at": datetime.fromisoformat(row[5]),
                }
            return None
        finally:
            conn.close()

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def create_order(
        self, reservation_id: int, sku: str, quantity: int
    ) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO orders (reservation_id, sku, quantity, created_at)
                   VALUES (?, ?, ?, ?)""",
                (reservation_id, sku, quantity, datetime.utcnow()),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_order(self, order_id: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """SELECT id, reservation_id, sku, quantity, created_at
                   FROM orders WHERE id = ?""",
                (order_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "reservation_id": row[1],
                    "sku": row[2],
                    "quantity": row[3],
                    "created_at": datetime.fromisoformat(row[4]),
                }
            return None
        finally:
            conn.close()

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[list, int]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM orders")
            total = cursor.fetchone()[0]

            offset = (page - 1) * size
            cursor.execute(
                """SELECT id, reservation_id, sku, quantity, created_at
                   FROM orders ORDER BY id DESC LIMIT ? OFFSET ?""",
                (size, offset),
            )
            rows = cursor.fetchall()
            orders = [
                {
                    "id": row[0],
                    "reservation_id": row[1],
                    "sku": row[2],
                    "quantity": row[3],
                    "created_at": datetime.fromisoformat(row[4]),
                }
                for row in rows
            ]
            return orders, total
        finally:
            conn.close()

    def clear_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM orders")
            cursor.execute("DELETE FROM reservations")
            cursor.execute("DELETE FROM skus")
            conn.commit()
        finally:
            conn.close()
