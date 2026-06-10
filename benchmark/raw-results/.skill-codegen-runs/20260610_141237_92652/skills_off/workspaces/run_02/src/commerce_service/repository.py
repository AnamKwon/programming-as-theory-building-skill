import sqlite3
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path


DB_PATH = Path.home() / ".cache" / "commerce_service.db"


class Repository:
    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = db_path
        self.init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT UNIQUE NOT NULL,
                    available_stock INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id INTEGER NOT NULL,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    confirmed_at TIMESTAMP,
                    FOREIGN KEY (sku_id) REFERENCES skus(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reservation_id INTEGER NOT NULL UNIQUE,
                    created_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (reservation_id) REFERENCES reservations(id)
                )
            """)
            conn.commit()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow()
            cursor.execute(
                "INSERT INTO skus (sku, available_stock, created_at) VALUES (?, ?, ?)",
                (sku, initial_stock, now),
            )
            conn.commit()
            sku_id = cursor.lastrowid
            return {"id": sku_id, "sku": sku, "available_stock": initial_stock}

    def get_sku_by_code(self, sku: str) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, sku, available_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def adjust_stock(self, sku: str, amount: int) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
                (amount, sku),
            )
            if cursor.rowcount == 0:
                return None
            conn.commit()
            cursor.execute("SELECT id, sku, available_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, key: str) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, sku, quantity, status, created_at, confirmed_at
                   FROM reservations WHERE idempotency_key = ?""",
                (key,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_reservation(
        self, sku_id: int, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow()
            cursor.execute(
                """INSERT INTO reservations
                   (sku_id, sku, quantity, status, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (sku_id, sku, quantity, "PENDING", idempotency_key, now),
            )
            conn.commit()
            reservation_id = cursor.lastrowid
            return {
                "id": reservation_id,
                "sku": sku,
                "quantity": quantity,
                "status": "PENDING",
                "created_at": now,
                "confirmed_at": None,
            }

    def get_reservation(self, reservation_id: int) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, sku, quantity, status, created_at, confirmed_at
                   FROM reservations WHERE id = ?""",
                (reservation_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_reservation_status(
        self, reservation_id: int, new_status: str, confirmed_at: datetime | None = None
    ) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if confirmed_at:
                cursor.execute(
                    """UPDATE reservations SET status = ?, confirmed_at = ? WHERE id = ?""",
                    (new_status, confirmed_at, reservation_id),
                )
            else:
                cursor.execute(
                    """UPDATE reservations SET status = ? WHERE id = ?""",
                    (new_status, reservation_id),
                )
            conn.commit()
            return cursor.rowcount > 0

    def create_order(self, reservation_id: int) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow()
            cursor.execute(
                "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
                (reservation_id, now),
            )
            conn.commit()
            order_id = cursor.lastrowid
            return {"id": order_id, "reservation_id": reservation_id, "created_at": now}

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            offset = (page - 1) * size

            cursor.execute("SELECT COUNT(*) as count FROM orders")
            total = cursor.fetchone()["count"]

            cursor.execute(
                """SELECT id, reservation_id, created_at FROM orders
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (size, offset),
            )
            rows = cursor.fetchall()
            items = [dict(row) for row in rows]

            total_pages = (total + size - 1) // size
            return {
                "items": items,
                "total": total,
                "page": page,
                "size": size,
                "total_pages": total_pages,
            }
