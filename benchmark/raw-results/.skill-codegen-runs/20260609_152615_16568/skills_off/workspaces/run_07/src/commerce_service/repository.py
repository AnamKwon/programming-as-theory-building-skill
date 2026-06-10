import sqlite3
from datetime import datetime
from typing import Optional

from .models import ReservationStatus, OrderStatus


class Database:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL UNIQUE,
                quantity INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                order_id INTEGER,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus (id),
                FOREIGN KEY (order_id) REFERENCES orders (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, name: str) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO skus (sku, name, created_at) VALUES (?, ?, ?)",
                (sku, name, datetime.utcnow().isoformat()),
            )
            conn.commit()
            sku_id = cursor.lastrowid
            cursor.execute("INSERT INTO stock (sku_id, quantity, updated_at) VALUES (?, ?, ?)",
                          (sku_id, 0, datetime.utcnow().isoformat()))
            conn.commit()
            return {"id": sku_id, "sku": sku, "name": name}
        finally:
            conn.close()

    def get_sku_by_code(self, sku: str) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, sku, name FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def adjust_stock(self, sku_id: int, quantity_delta: int) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT quantity FROM stock WHERE sku_id = ?", (sku_id,))
            row = cursor.fetchone()
            old_qty = dict(row)["quantity"] if row else 0
            new_qty = old_qty + quantity_delta
            cursor.execute(
                "UPDATE stock SET quantity = ?, updated_at = ? WHERE sku_id = ?",
                (new_qty, datetime.utcnow().isoformat(), sku_id),
            )
            conn.commit()
            return {"sku_id": sku_id, "old_quantity": old_qty, "new_quantity": new_qty}
        finally:
            conn.close()

    def get_available_stock(self, sku_id: int) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT quantity FROM stock WHERE sku_id = ?
                """,
                (sku_id,),
            )
            row = cursor.fetchone()
            return dict(row)["quantity"] if row else 0
        finally:
            conn.close()

    def get_reserved_quantity(self, sku_id: int) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT COALESCE(SUM(quantity), 0) as total
                FROM reservations
                WHERE sku_id = ? AND status IN (?, ?)
                """,
                (sku_id, ReservationStatus.PENDING, ReservationStatus.CONFIRMED),
            )
            row = cursor.fetchone()
            return dict(row)["total"] if row else 0
        finally:
            conn.close()

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        customer_id: str,
        idempotency_key: str,
        expires_at: str,
    ) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """
                INSERT INTO reservations
                (sku_id, quantity, status, customer_id, idempotency_key, created_at, expires_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sku_id,
                    quantity,
                    ReservationStatus.PENDING,
                    customer_id,
                    idempotency_key,
                    now,
                    expires_at,
                    now,
                ),
            )
            conn.commit()
            reservation_id = cursor.lastrowid
            return {"id": reservation_id}
        finally:
            conn.close()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT r.id, s.sku, r.quantity, r.status, r.customer_id,
                       r.created_at, r.expires_at, r.order_id
                FROM reservations r
                JOIN skus s ON r.sku_id = s.id
                WHERE r.idempotency_key = ?
                """,
                (idempotency_key,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT r.id, s.sku, r.quantity, r.status, r.customer_id,
                       r.created_at, r.expires_at, r.order_id
                FROM reservations r
                JOIN skus s ON r.sku_id = s.id
                WHERE r.id = ?
                """,
                (reservation_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_reservation_status(self, reservation_id: int, status: str) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE reservations SET status = ?, updated_at = ? WHERE id = ?",
                (status, datetime.utcnow().isoformat(), reservation_id),
            )
            conn.commit()
        finally:
            conn.close()

    def create_order(self, customer_id: str) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """
                INSERT INTO orders (status, customer_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (OrderStatus.PENDING, customer_id, now, now),
            )
            conn.commit()
            order_id = cursor.lastrowid
            return {"id": order_id}
        finally:
            conn.close()

    def link_reservation_to_order(self, reservation_id: int, order_id: int) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE reservations SET order_id = ?, updated_at = ? WHERE id = ?",
                (order_id, datetime.utcnow().isoformat(), reservation_id),
            )
            conn.commit()
        finally:
            conn.close()

    def confirm_order(self, order_id: int) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
                (OrderStatus.CONFIRMED, datetime.utcnow().isoformat(), order_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_order(self, order_id: int) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, status, customer_id, created_at, updated_at FROM orders WHERE id = ?",
                (order_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_orders(self, customer_id: str, page: int = 1, page_size: int = 10) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) as count FROM orders WHERE customer_id = ?", (customer_id,))
            total = dict(cursor.fetchone())["count"]

            offset = (page - 1) * page_size
            cursor.execute(
                """
                SELECT id, status, customer_id, created_at, updated_at
                FROM orders WHERE customer_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (customer_id, page_size, offset),
            )
            orders = [dict(row) for row in cursor.fetchall()]
            return {"orders": orders, "total": total, "page": page, "page_size": page_size}
        finally:
            conn.close()

    def get_order_items(self, order_id: int) -> list[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT s.sku, r.quantity, r.status
                FROM reservations r
                JOIN skus s ON r.sku_id = s.id
                WHERE r.order_id = ?
                """,
                (order_id,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_expired_reservations(self, now: str) -> list[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id FROM reservations
                WHERE status = ? AND expires_at <= ?
                """,
                (ReservationStatus.PENDING, now),
            )
            return [dict(row)["id"] for row in cursor.fetchall()]
        finally:
            conn.close()
