import sqlite3
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
from contextlib import contextmanager


DATABASE_URL = "commerce.db"


@contextmanager
def get_connection():
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                available_stock INTEGER NOT NULL,
                total_stock INTEGER NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            )
        ''')

        conn.commit()


class SKURepository:
    @staticmethod
    def create_sku(sku: str, initial_stock: int) -> int:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO skus (sku, available_stock, total_stock)
                   VALUES (?, ?, ?)''',
                (sku, initial_stock, initial_stock)
            )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def get_by_sku(sku: str) -> Optional[Dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM skus WHERE sku = ?', (sku,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    @staticmethod
    def get_by_id(sku_id: int) -> Optional[Dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM skus WHERE id = ?', (sku_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    @staticmethod
    def adjust_stock(sku: str, amount: int) -> Optional[Dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('SELECT id FROM skus WHERE sku = ?', (sku,))
            row = cursor.fetchone()
            if not row:
                return None

            sku_id = row[0]
            cursor.execute(
                '''UPDATE skus SET available_stock = available_stock + ?
                   WHERE id = ?''',
                (amount, sku_id)
            )
            conn.commit()

            cursor.execute('SELECT * FROM skus WHERE id = ?', (sku_id,))
            result = cursor.fetchone()
            return dict(result)


class ReservationRepository:
    @staticmethod
    def create_reservation(sku_id: int, quantity: int, idempotency_key: str) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat() + "Z"
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO reservations
                   (sku_id, quantity, idempotency_key, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (sku_id, quantity, idempotency_key, "PENDING", now, now)
            )
            conn.commit()
            reservation_id = cursor.lastrowid

            return ReservationRepository.get_by_id(reservation_id)

    @staticmethod
    def get_by_id(reservation_id: int) -> Dict[str, Any]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''SELECT r.id, s.sku, r.quantity, r.idempotency_key,
                          r.status, r.created_at, r.updated_at
                   FROM reservations r
                   JOIN skus s ON r.sku_id = s.id
                   WHERE r.id = ?''',
                (reservation_id,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    @staticmethod
    def get_by_idempotency_key(idempotency_key: str) -> Optional[Dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''SELECT r.id, s.sku, r.quantity, r.idempotency_key,
                          r.status, r.created_at, r.updated_at
                   FROM reservations r
                   JOIN skus s ON r.sku_id = s.id
                   WHERE r.idempotency_key = ?''',
                (idempotency_key,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    @staticmethod
    def update_status(reservation_id: int, status: str) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat() + "Z"
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''UPDATE reservations SET status = ?, updated_at = ?
                   WHERE id = ?''',
                (status, now, reservation_id)
            )
            conn.commit()
            return ReservationRepository.get_by_id(reservation_id)

    @staticmethod
    def get_quantity_by_id(reservation_id: int) -> Optional[int]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT quantity FROM reservations WHERE id = ?', (reservation_id,))
            row = cursor.fetchone()
            if row:
                return row[0]
            return None

    @staticmethod
    def get_sku_id_by_id(reservation_id: int) -> Optional[int]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT sku_id FROM reservations WHERE id = ?', (reservation_id,))
            row = cursor.fetchone()
            if row:
                return row[0]
            return None


class OrderRepository:
    @staticmethod
    def create_order(reservation_id: int) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat() + "Z"
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO orders (reservation_id, created_at)
                   VALUES (?, ?)''',
                (reservation_id, now)
            )
            conn.commit()
            order_id = cursor.lastrowid
            return OrderRepository.get_by_id(order_id)

    @staticmethod
    def get_by_id(order_id: int) -> Dict[str, Any]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, reservation_id, created_at FROM orders WHERE id = ?', (order_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    @staticmethod
    def get_orders_paginated(page: int, size: int) -> Tuple[List[Dict[str, Any]], int]:
        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) as total FROM orders')
            total = cursor.fetchone()[0]

            offset = (page - 1) * size
            cursor.execute(
                '''SELECT id, reservation_id, created_at FROM orders
                   ORDER BY created_at DESC
                   LIMIT ? OFFSET ?''',
                (size, offset)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows], total
