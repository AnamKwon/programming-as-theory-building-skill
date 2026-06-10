import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager
from pathlib import Path


DB_PATH = Path("commerce.db")
RESERVATION_EXPIRY_MINUTES = 30


class Repository:
    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = db_path

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY,
                    sku_code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    stock INTEGER NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY,
                    sku_id INTEGER NOT NULL,
                    order_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus(id),
                    FOREIGN KEY (order_id) REFERENCES orders(id)
                )
            """)

    def create_sku(self, sku_code: str, name: str, initial_stock: int) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO skus (sku_code, name, stock) VALUES (?, ?, ?)",
                (sku_code, name, initial_stock),
            )
            sku_id = cursor.lastrowid
        return self.get_sku(sku_id)

    def get_sku(self, sku_id: int) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, sku_code, name, stock FROM skus WHERE id = ?", (sku_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_sku_by_code(self, sku_code: str) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, sku_code, name, stock FROM skus WHERE sku_code = ?", (sku_code,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def adjust_stock(self, sku_id: int, quantity: int) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET stock = stock + ? WHERE id = ?",
                (quantity, sku_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"SKU {sku_id} not found")
            cursor.execute("SELECT stock FROM skus WHERE id = ?", (sku_id,))
            return cursor.fetchone()[0]

    def create_order(self) -> dict:
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO orders (status, created_at) VALUES (?, ?)",
                ("pending", now),
            )
            order_id = cursor.lastrowid
        return self.get_order(order_id)

    def get_order(self, order_id: int) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, status, created_at FROM orders WHERE id = ?",
                (order_id,),
            )
            order_row = cursor.fetchone()
            if not order_row:
                return None

            cursor.execute(
                """SELECT id, sku_id, quantity, status, expires_at
                   FROM reservations WHERE order_id = ? ORDER BY id""",
                (order_id,),
            )
            reservations = [dict(row) for row in cursor.fetchall()]

            order = dict(order_row)
            order["reservations"] = reservations
            return order

    def list_orders(self, offset: int = 0, limit: int = 20) -> tuple[list[dict], int]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM orders")
            total = cursor.fetchone()[0]

            cursor.execute(
                "SELECT id, status, created_at FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            order_rows = cursor.fetchall()

            orders = []
            for order_row in order_rows:
                order = dict(order_row)
                cursor.execute(
                    """SELECT id, sku_id, quantity, status, expires_at
                       FROM reservations WHERE order_id = ? ORDER BY id""",
                    (order["id"],),
                )
                order["reservations"] = [dict(row) for row in cursor.fetchall()]
                orders.append(order)

        return orders, total

    def create_reservation(
        self,
        sku_id: int,
        order_id: int,
        quantity: int,
        idempotency_key: str,
    ) -> dict:
        now = datetime.utcnow()
        expires_at = (now + timedelta(minutes=RESERVATION_EXPIRY_MINUTES)).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO reservations
                   (sku_id, order_id, quantity, status, idempotency_key, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (sku_id, order_id, quantity, "reserved", idempotency_key, now.isoformat(), expires_at),
            )
            reservation_id = cursor.lastrowid

        return self.get_reservation(reservation_id)

    def get_reservation(self, reservation_id: int) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, sku_id, order_id, quantity, status, idempotency_key,
                          created_at, expires_at FROM reservations WHERE id = ?""",
                (reservation_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, sku_id, order_id, quantity, status, idempotency_key,
                          created_at, expires_at FROM reservations WHERE idempotency_key = ?""",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Reservation {reservation_id} not found")

        return self.get_reservation(reservation_id)
