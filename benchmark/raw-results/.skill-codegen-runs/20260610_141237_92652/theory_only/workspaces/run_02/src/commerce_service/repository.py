import sqlite3
from datetime import datetime
from typing import Optional, List, Tuple


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS skus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE NOT NULL,
            available_stock INTEGER NOT NULL,
            total_stock INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku_id INTEGER NOT NULL,
            sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            idempotency_key TEXT UNIQUE NOT NULL,
            FOREIGN KEY (sku_id) REFERENCES skus(id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (reservation_id) REFERENCES reservations(id)
        )
        ''')

        conn.commit()
        conn.close()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        created_at = datetime.utcnow().isoformat()

        cursor.execute(
            '''INSERT INTO skus (sku, available_stock, total_stock, created_at)
               VALUES (?, ?, ?, ?)''',
            (sku, initial_stock, initial_stock, created_at)
        )
        conn.commit()
        sku_id = cursor.lastrowid
        conn.close()

        return {
            'id': sku_id,
            'sku': sku,
            'available_stock': initial_stock,
            'total_stock': initial_stock,
            'created_at': created_at
        }

    def get_sku_by_name(self, sku: str) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM skus WHERE sku = ?', (sku,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM skus WHERE sku = ?', (sku,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return None

        new_stock = row['available_stock'] + amount
        cursor.execute(
            'UPDATE skus SET available_stock = ? WHERE sku = ?',
            (new_stock, sku)
        )
        conn.commit()
        conn.close()

        return {
            'id': row['id'],
            'sku': row['sku'],
            'available_stock': new_stock,
            'total_stock': row['total_stock'],
            'created_at': row['created_at']
        }

    def create_reservation(self, sku_id: int, sku: str, quantity: int, idempotency_key: str) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        created_at = datetime.utcnow().isoformat()

        cursor.execute(
            '''INSERT INTO reservations (sku_id, sku, quantity, status, created_at, idempotency_key)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (sku_id, sku, quantity, 'PENDING', created_at, idempotency_key)
        )
        conn.commit()
        reservation_id = cursor.lastrowid
        conn.close()

        return {
            'id': reservation_id,
            'sku': sku,
            'quantity': quantity,
            'status': 'PENDING',
            'created_at': created_at,
            'idempotency_key': idempotency_key
        }

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM reservations WHERE idempotency_key = ?', (key,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM reservations WHERE id = ?', (reservation_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE reservations SET status = ? WHERE id = ?',
            (status, reservation_id)
        )
        conn.commit()
        conn.close()
        return True

    def create_order(self, reservation_id: int) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        created_at = datetime.utcnow().isoformat()

        cursor.execute(
            'INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)',
            (reservation_id, created_at)
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()

        return {
            'id': order_id,
            'reservation_id': reservation_id,
            'created_at': created_at
        }

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[List[dict], int]:
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) as count FROM orders')
        total = cursor.fetchone()['count']

        offset = (page - 1) * size
        cursor.execute(
            'SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (size, offset)
        )
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows], total
