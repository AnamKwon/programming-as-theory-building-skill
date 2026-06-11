import sqlite3
from datetime import datetime
from contextlib import contextmanager
from threading import Lock


class Repository:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.lock = Lock()
        self._conn = None
        if db_path == ":memory:":
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        self._init_db()

    @contextmanager
    def _get_connection(self):
        if self._conn is not None:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        else:
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

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    sku TEXT PRIMARY KEY,
                    stock INTEGER NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
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
                    timestamp DATETIME NOT NULL,
                    FOREIGN KEY (reservation_id) REFERENCES reservations(id),
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                )
            """)

    def create_sku(self, sku: str, initial_stock: int) -> bool:
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        "INSERT INTO skus (sku, stock) VALUES (?, ?)",
                        (sku, initial_stock),
                    )
                    return True
                except sqlite3.IntegrityError:
                    return False

    def get_sku_stock(self, sku: str) -> int | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return row["stock"] if row else None

    def adjust_stock(self, sku: str, amount: int) -> int | None:
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
                row = cursor.fetchone()
                if not row:
                    return None
                new_stock = row["stock"] + amount
                cursor.execute(
                    "UPDATE skus SET stock = ? WHERE sku = ?",
                    (new_stock, sku),
                )
                return new_stock

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str,
        status: str = "PENDING",
    ) -> int | None:
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        """INSERT INTO reservations
                           (sku, quantity, status, timestamp, idempotency_key)
                           VALUES (?, ?, ?, ?, ?)""",
                        (sku, quantity, status, datetime.utcnow().isoformat(), idempotency_key),
                    )
                    return cursor.lastrowid
                except sqlite3.IntegrityError:
                    return None

    def get_reservation(self, reservation_id: int) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM reservations WHERE id = ?",
                (reservation_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row)

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM reservations WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row)

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> bool:
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE reservations SET status = ? WHERE id = ?",
                    (status, reservation_id),
                )
                return cursor.rowcount > 0

    def create_order(
        self, reservation_id: int, sku: str, quantity: int
    ) -> int | None:
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        """INSERT INTO orders
                           (reservation_id, sku, quantity, timestamp)
                           VALUES (?, ?, ?, ?)""",
                        (reservation_id, sku, quantity, datetime.utcnow().isoformat()),
                    )
                    return cursor.lastrowid
                except sqlite3.IntegrityError:
                    return None

    def get_order(self, order_id: int) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row)

    def list_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM orders")
            total = cursor.fetchone()["total"]

            offset = (page - 1) * size
            cursor.execute(
                "SELECT * FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
                (size, offset),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows], total
