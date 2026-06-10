import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager


DATABASE_PATH = Path("commerce.db")


class Database:
    def __init__(self, db_path: str = str(DATABASE_PATH)):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                available_stock INTEGER NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id),
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        ''')

        conn.commit()
        conn.close()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO skus (sku, available_stock) VALUES (?, ?)',
                (sku, initial_stock)
            )
            conn.commit()
            cursor.execute('SELECT id, sku, available_stock FROM skus WHERE id = ?', (cursor.lastrowid,))
            row = cursor.fetchone()
            return dict(row)

    def get_sku_by_name(self, sku: str) -> dict | None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, sku, available_stock FROM skus WHERE sku = ?', (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def adjust_stock(self, sku: str, amount: int) -> dict:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT available_stock FROM skus WHERE sku = ?', (sku,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"SKU {sku} not found")

            new_stock = row[0] + amount
            cursor.execute('UPDATE skus SET available_stock = ? WHERE sku = ?', (new_stock, sku))
            conn.commit()
            return {"sku": sku, "available_stock": new_stock}

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                'INSERT INTO reservations (sku, quantity, status, idempotency_key, created_at) VALUES (?, ?, ?, ?, ?)',
                (sku, quantity, 'PENDING', idempotency_key, now)
            )
            conn.commit()
            cursor.execute('SELECT id, sku, quantity, status, created_at FROM reservations WHERE id = ?', (cursor.lastrowid,))
            row = cursor.fetchone()
            return dict(row)

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, sku, quantity, status, created_at FROM reservations WHERE idempotency_key = ?', (idempotency_key,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_reservation(self, reservation_id: int) -> dict | None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, sku, quantity, status, created_at FROM reservations WHERE id = ?', (reservation_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE reservations SET status = ? WHERE id = ?', (status, reservation_id))
            conn.commit()

    def create_order(self, reservation_id: int, sku: str, quantity: int) -> dict:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                'INSERT INTO orders (reservation_id, sku, quantity, created_at) VALUES (?, ?, ?, ?)',
                (reservation_id, sku, quantity, now)
            )
            conn.commit()
            cursor.execute('SELECT id, reservation_id, sku, quantity, created_at FROM orders WHERE id = ?', (cursor.lastrowid,))
            row = cursor.fetchone()
            return dict(row)

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            offset = (page - 1) * size
            cursor.execute('SELECT COUNT(*) FROM orders')
            total = cursor.fetchone()[0]
            cursor.execute('SELECT id, reservation_id, sku, quantity, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?', (size, offset))
            rows = cursor.fetchall()
            return [dict(row) for row in rows], total
