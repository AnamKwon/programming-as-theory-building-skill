import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager


DB_PATH = "commerce.db"


@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db_connection() as conn:
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
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
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


class Repository:
    def create_sku(self, sku: str, initial_stock: int) -> bool:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
                    (sku, initial_stock)
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def get_sku_stock(self, sku: str) -> int | None:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return row[0] if row else None

    def adjust_stock(self, sku: str, amount: int) -> int | None:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
                (amount, sku)
            )
            if cursor.rowcount == 0:
                return None
            conn.commit()
            cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return row[0] if row else None

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict | None:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            created_at = datetime.utcnow().isoformat()
            try:
                cursor.execute(
                    """INSERT INTO reservations (sku, quantity, status, created_at, idempotency_key)
                       VALUES (?, ?, 'PENDING', ?, ?)""",
                    (sku, quantity, created_at, idempotency_key)
                )
                conn.commit()
                reservation_id = cursor.lastrowid
                return {
                    "id": reservation_id,
                    "sku": sku,
                    "quantity": quantity,
                    "status": "PENDING",
                    "created_at": created_at,
                    "idempotency_key": idempotency_key,
                }
            except sqlite3.IntegrityError:
                return None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, sku, quantity, status, created_at, idempotency_key FROM reservations WHERE idempotency_key = ?",
                (idempotency_key,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "sku": row[1],
                    "quantity": row[2],
                    "status": row[3],
                    "created_at": row[4],
                    "idempotency_key": row[5],
                }
            return None

    def get_reservation(self, reservation_id: int) -> dict | None:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, sku, quantity, status, created_at, idempotency_key FROM reservations WHERE id = ?",
                (reservation_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "sku": row[1],
                    "quantity": row[2],
                    "status": row[3],
                    "created_at": row[4],
                    "idempotency_key": row[5],
                }
            return None

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def create_order(self, reservation_id: int, sku: str, quantity: int) -> int | None:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            created_at = datetime.utcnow().isoformat()
            try:
                cursor.execute(
                    """INSERT INTO orders (reservation_id, sku, quantity, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (reservation_id, sku, quantity, created_at)
                )
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                return None

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            offset = (page - 1) * size
            cursor.execute(
                "SELECT id, reservation_id, sku, quantity, created_at FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
                (size, offset)
            )
            orders = []
            for row in cursor.fetchall():
                orders.append({
                    "id": row[0],
                    "reservation_id": row[1],
                    "sku": row[2],
                    "quantity": row[3],
                    "created_at": row[4],
                })

            cursor.execute("SELECT COUNT(*) FROM orders")
            total = cursor.fetchone()[0]

            return orders, total
