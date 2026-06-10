import sqlite3
import uuid
from datetime import datetime


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS skus (
                sku TEXT PRIMARY KEY,
                available_stock INTEGER NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reservations (
                id TEXT PRIMARY KEY,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                FOREIGN KEY(sku) REFERENCES skus(sku)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                reservation_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY(reservation_id) REFERENCES reservations(id)
            )
        ''')

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO skus (sku, available_stock) VALUES (?, ?)',
            (sku, initial_stock)
        )
        conn.commit()
        conn.close()
        return {"sku": sku, "available_stock": initial_stock}

    def adjust_stock(self, sku: str, amount: int) -> dict:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?',
            (amount, sku)
        )
        cursor.execute('SELECT available_stock FROM skus WHERE sku = ?', (sku,))
        result = cursor.fetchone()
        conn.commit()
        conn.close()
        return {"sku": sku, "available_stock": result[0] if result else 0}

    def get_sku_stock(self, sku: str) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT available_stock FROM skus WHERE sku = ?', (sku,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        reservation_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        cursor.execute('''
            INSERT INTO reservations (id, sku, quantity, status, created_at, idempotency_key)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (reservation_id, sku, quantity, "PENDING", now, idempotency_key))

        cursor.execute(
            'UPDATE skus SET available_stock = available_stock - ? WHERE sku = ?',
            (quantity, sku)
        )

        conn.commit()
        conn.close()

        return {
            "id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "status": "PENDING",
            "created_at": now
        }

    def get_reservation(self, reservation_id: str) -> dict | None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, sku, quantity, status, created_at FROM reservations WHERE id = ?',
            (reservation_id,)
        )
        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                "id": result[0],
                "sku": result[1],
                "quantity": result[2],
                "status": result[3],
                "created_at": result[4]
            }
        return None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, sku, quantity, status, created_at FROM reservations WHERE idempotency_key = ?',
            (idempotency_key,)
        )
        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                "id": result[0],
                "sku": result[1],
                "quantity": result[2],
                "status": result[3],
                "created_at": result[4]
            }
        return None

    def update_reservation_status(self, reservation_id: str, status: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE reservations SET status = ? WHERE id = ?',
            (status, reservation_id)
        )
        conn.commit()
        conn.close()
        return True

    def create_order(self, reservation_id: str) -> dict:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        order_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        cursor.execute(
            'INSERT INTO orders (id, reservation_id, created_at) VALUES (?, ?, ?)',
            (order_id, reservation_id, now)
        )

        conn.commit()
        conn.close()

        return {
            "id": order_id,
            "reservation_id": reservation_id,
            "created_at": now
        }

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        offset = (page - 1) * size

        cursor.execute('SELECT COUNT(*) FROM orders')
        total = cursor.fetchone()[0]

        cursor.execute('''
            SELECT id, reservation_id, created_at FROM orders
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (size, offset))

        results = cursor.fetchall()
        conn.close()

        orders = [
            {
                "id": r[0],
                "reservation_id": r[1],
                "created_at": r[2]
            }
            for r in results
        ]

        return {
            "orders": orders,
            "page": page,
            "size": size,
            "total": total
        }
