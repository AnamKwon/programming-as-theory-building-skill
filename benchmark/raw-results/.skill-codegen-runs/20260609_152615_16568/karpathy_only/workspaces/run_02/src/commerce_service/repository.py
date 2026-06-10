import sqlite3
from datetime import datetime, timedelta
from typing import Optional
import uuid


DATABASE_URL = "sqlite:///./commerce.db"
DB_PATH = "commerce.db"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS skus (
            sku_id TEXT PRIMARY KEY,
            stock INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            reservation_id TEXT PRIMARY KEY,
            sku_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            status TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            reservation_id TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (reservation_id) REFERENCES reservations(reservation_id),
            FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
        )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_reservations_sku ON reservations(sku_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_reservations_idempotency ON reservations(idempotency_key)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_orders_sku ON orders(sku_id)")

    conn.commit()
    conn.close()


class SKURepository:
    @staticmethod
    def create(sku_id: str, stock: int) -> dict:
        conn = get_db_connection()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute(
            "INSERT INTO skus (sku_id, stock, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (sku_id, stock, now, now),
        )
        conn.commit()
        conn.close()
        return {"sku_id": sku_id, "stock": stock}

    @staticmethod
    def get(sku_id: str) -> Optional[dict]:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT sku_id, stock FROM skus WHERE sku_id = ?", (sku_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def adjust_stock(sku_id: str, delta: int) -> dict:
        conn = get_db_connection()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute(
            "UPDATE skus SET stock = stock + ?, updated_at = ? WHERE sku_id = ?",
            (delta, now, sku_id),
        )
        conn.commit()
        c.execute("SELECT sku_id, stock FROM skus WHERE sku_id = ?", (sku_id,))
        row = c.fetchone()
        conn.close()
        return dict(row)


class ReservationRepository:
    @staticmethod
    def create(sku_id: str, quantity: int, idempotency_key: str) -> dict:
        conn = get_db_connection()
        c = conn.cursor()
        reservation_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        expires_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat()

        c.execute(
            """INSERT INTO reservations
               (reservation_id, sku_id, quantity, status, idempotency_key, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (reservation_id, sku_id, quantity, "pending", idempotency_key, now, expires_at),
        )
        conn.commit()
        conn.close()
        return {
            "reservation_id": reservation_id,
            "sku_id": sku_id,
            "quantity": quantity,
            "status": "pending",
            "expires_at": expires_at,
        }

    @staticmethod
    def get_by_idempotency_key(idempotency_key: str) -> Optional[dict]:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT reservation_id, sku_id, quantity, status, expires_at FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get(reservation_id: str) -> Optional[dict]:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT reservation_id, sku_id, quantity, status, expires_at FROM reservations WHERE reservation_id = ?",
            (reservation_id,),
        )
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def update_status(reservation_id: str, status: str):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "UPDATE reservations SET status = ? WHERE reservation_id = ?",
            (status, reservation_id),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def count_active_by_sku(sku_id: str) -> int:
        conn = get_db_connection()
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        c.execute(
            "SELECT COUNT(*) as cnt FROM reservations WHERE sku_id = ? AND status = 'pending' AND expires_at > ?",
            (sku_id, now),
        )
        row = c.fetchone()
        conn.close()
        return row["cnt"] if row else 0


class OrderRepository:
    @staticmethod
    def create(reservation_id: str, sku_id: str, quantity: int) -> dict:
        conn = get_db_connection()
        c = conn.cursor()
        order_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        c.execute(
            """INSERT INTO orders (order_id, reservation_id, sku_id, quantity, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (order_id, reservation_id, sku_id, quantity, "reserved", now),
        )
        conn.commit()
        conn.close()
        return {
            "order_id": order_id,
            "sku_id": sku_id,
            "quantity": quantity,
            "status": "reserved",
            "created_at": now,
        }

    @staticmethod
    def get(order_id: str) -> Optional[dict]:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT order_id, sku_id, quantity, status, created_at FROM orders WHERE order_id = ?",
            (order_id,),
        )
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def update_status(order_id: str, status: str):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "UPDATE orders SET status = ? WHERE order_id = ?",
            (status, order_id),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def list_all(limit: int, offset: int) -> tuple[list[dict], int]:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM orders")
        total = c.fetchone()["cnt"]
        c.execute(
            "SELECT order_id, sku_id, quantity, status, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows], total

    @staticmethod
    def get_by_reservation_id(reservation_id: str) -> Optional[dict]:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT order_id, sku_id, quantity, status, created_at FROM orders WHERE reservation_id = ?",
            (reservation_id,),
        )
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None
