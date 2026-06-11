import sqlite3
from datetime import datetime
from pathlib import Path


DATABASE_PATH = Path(__file__).parent.parent.parent / "commerce.db"


class Repository:
    def __init__(self, db_path: str | Path = DATABASE_PATH):
        self.db_path = db_path

    def _get_conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                available_stock INTEGER NOT NULL,
                reserved_stock INTEGER NOT NULL DEFAULT 0
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS idempotency_log (
                idempotency_key TEXT PRIMARY KEY,
                response_json TEXT NOT NULL
            )
        ''')

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO skus (sku, available_stock, reserved_stock) VALUES (?, ?, ?)',
            (sku, initial_stock, 0)
        )
        conn.commit()
        conn.close()
        return {'sku': sku, 'available_stock': initial_stock, 'reserved_stock': 0}

    def get_sku(self, sku: str) -> dict | None:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT sku, available_stock, reserved_stock FROM skus WHERE sku = ?', (sku,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def adjust_stock(self, sku: str, amount: int) -> dict | None:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT available_stock FROM skus WHERE sku = ?', (sku,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        new_stock = row['available_stock'] + amount
        cursor.execute('UPDATE skus SET available_stock = ? WHERE sku = ?', (new_stock, sku))
        conn.commit()

        cursor.execute('SELECT available_stock, reserved_stock FROM skus WHERE sku = ?', (sku,))
        updated = cursor.fetchone()
        conn.close()
        return dict(updated)

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute(
            '''INSERT INTO reservations (sku, quantity, status, created_at, idempotency_key)
               VALUES (?, ?, ?, ?, ?)''',
            (sku, quantity, 'PENDING', now, idempotency_key)
        )
        conn.commit()
        reservation_id = cursor.lastrowid

        cursor.execute('UPDATE skus SET reserved_stock = reserved_stock + ? WHERE sku = ?', (quantity, sku))
        cursor.execute('UPDATE skus SET available_stock = available_stock - ? WHERE sku = ?', (quantity, sku))
        conn.commit()
        conn.close()

        return {
            'id': reservation_id,
            'sku': sku,
            'quantity': quantity,
            'status': 'PENDING',
            'created_at': now,
            'idempotency_key': idempotency_key
        }

    def get_reservation(self, reservation_id: int) -> dict | None:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, sku, quantity, status, created_at, idempotency_key FROM reservations WHERE id = ?',
            (reservation_id,)
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, sku, quantity, status, created_at, idempotency_key FROM reservations WHERE idempotency_key = ?',
            (idempotency_key,)
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('UPDATE reservations SET status = ? WHERE id = ?', (status, reservation_id))
        conn.commit()
        conn.close()
        return True

    def create_order(self, reservation_id: int, sku: str, quantity: int) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute(
            'INSERT INTO orders (reservation_id, sku, quantity, created_at) VALUES (?, ?, ?, ?)',
            (reservation_id, sku, quantity, now)
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()

        return {
            'id': order_id,
            'reservation_id': reservation_id,
            'sku': sku,
            'quantity': quantity,
            'created_at': now
        }

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) as total FROM orders')
        total = cursor.fetchone()['total']

        offset = (page - 1) * size
        cursor.execute(
            'SELECT id, reservation_id, sku, quantity, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (size, offset)
        )
        rows = cursor.fetchall()
        conn.close()

        orders = [dict(row) for row in rows]
        return orders, total

    def restore_reserved_stock(self, sku: str, quantity: int) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE skus SET available_stock = available_stock + ?, reserved_stock = reserved_stock - ? WHERE sku = ?',
            (quantity, quantity, sku)
        )
        conn.commit()
        conn.close()
