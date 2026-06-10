import sqlite3
from datetime import datetime
from typing import Optional, List, Tuple


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        if db_path == ":memory:":
            self.conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        else:
            self.conn = None
        self.init_db()

    def get_connection(self):
        if self.db_path == ":memory:":
            return self.conn
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn

    def init_db(self):
        conn = self.get_connection()
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
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            )
        """)

        conn.commit()
        if self.db_path != ":memory:":
            conn.close()

    def _close_conn(self, conn):
        if self.db_path != ":memory:":
            conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
            (sku, initial_stock),
        )
        conn.commit()
        sku_id = cursor.lastrowid
        self._close_conn(conn)
        return {"id": sku_id, "sku": sku, "available_stock": initial_stock}

    def get_sku_by_name(self, sku: str) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, available_stock FROM skus WHERE sku = ?", (sku,)
        )
        row = cursor.fetchone()
        self._close_conn(conn)
        return dict(row) if row else None

    def update_sku_stock(self, sku_id: int, new_stock: int) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE skus SET available_stock = ? WHERE id = ?", (new_stock, sku_id))
        conn.commit()
        cursor.execute(
            "SELECT id, sku, available_stock FROM skus WHERE id = ?", (sku_id,)
        )
        row = cursor.fetchone()
        self._close_conn(conn)
        return dict(row)

    def create_reservation(self, sku_id: int, quantity: int, idempotency_key: str) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute(
            "INSERT INTO reservations (sku_id, quantity, status, created_at, idempotency_key) VALUES (?, ?, ?, ?, ?)",
            (sku_id, quantity, "PENDING", now, idempotency_key),
        )
        conn.commit()
        res_id = cursor.lastrowid

        cursor.execute(
            "SELECT r.id, s.sku, r.quantity, r.status, r.created_at FROM reservations r JOIN skus s ON r.sku_id = s.id WHERE r.id = ?",
            (res_id,),
        )
        row = cursor.fetchone()
        self._close_conn(conn)
        return dict(row)

    def get_reservation_by_id(self, res_id: int) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT r.id, s.sku, r.quantity, r.status, r.created_at, r.sku_id FROM reservations r JOIN skus s ON r.sku_id = s.id WHERE r.id = ?",
            (res_id,),
        )
        row = cursor.fetchone()
        self._close_conn(conn)
        return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT r.id, s.sku, r.quantity, r.status, r.created_at FROM reservations r JOIN skus s ON r.sku_id = s.id WHERE r.idempotency_key = ?",
            (idempotency_key,),
        )
        row = cursor.fetchone()
        self._close_conn(conn)
        return dict(row) if row else None

    def update_reservation_status(self, res_id: int, status: str) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?", (status, res_id)
        )
        conn.commit()

        cursor.execute(
            "SELECT r.id, s.sku, r.quantity, r.status, r.created_at FROM reservations r JOIN skus s ON r.sku_id = s.id WHERE r.id = ?",
            (res_id,),
        )
        row = cursor.fetchone()
        self._close_conn(conn)
        return dict(row)

    def create_order(self, reservation_id: int) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute(
            "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
            (reservation_id, now),
        )
        conn.commit()
        order_id = cursor.lastrowid

        cursor.execute(
            "SELECT id, reservation_id, created_at FROM orders WHERE id = ?", (order_id,)
        )
        row = cursor.fetchone()
        self._close_conn(conn)
        return dict(row)

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[List[dict], int]:
        conn = self.get_connection()
        cursor = conn.cursor()

        offset = (page - 1) * size
        cursor.execute(
            "SELECT id, reservation_id, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (size, offset),
        )
        rows = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]

        self._close_conn(conn)
        return [dict(row) for row in rows], total
