import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple


class Database:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path

    @contextmanager
    def get_connection(self):
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

    def initialize_schema(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT UNIQUE NOT NULL,
                    initial_stock INTEGER NOT NULL,
                    available_stock INTEGER NOT NULL,
                    reserved_stock INTEGER NOT NULL DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT,
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


class SKURepository:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> Dict[str, Any]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO skus (sku, initial_stock, available_stock, reserved_stock) VALUES (?, ?, ?, ?)",
                (sku, initial_stock, initial_stock, 0),
            )
            cursor.execute("SELECT id FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return {"id": row["id"], "sku": sku, "initial_stock": initial_stock}

    def get_sku_by_name(self, sku: str) -> Optional[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, sku, available_stock, reserved_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def adjust_stock(self, sku: str, amount: int) -> Dict[str, Any]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, available_stock, reserved_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"SKU {sku} not found")

            new_available = row["available_stock"] + amount
            cursor.execute(
                "UPDATE skus SET available_stock = ? WHERE sku = ?",
                (new_available, sku),
            )
            return {
                "sku": sku,
                "available_stock": new_available,
                "reserved_stock": row["reserved_stock"],
            }


class ReservationRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT r.id, s.sku, r.quantity, r.idempotency_key, r.status, r.created_at
                   FROM reservations r
                   JOIN skus s ON r.sku_id = s.id
                   WHERE r.idempotency_key = ?""",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def create_reservation(
        self, sku_id: int, sku: str, quantity: int, idempotency_key: str
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO reservations (sku_id, quantity, idempotency_key, status, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (sku_id, quantity, idempotency_key, "PENDING", now),
            )
            cursor.execute(
                "SELECT id FROM reservations WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            return {
                "id": row["id"],
                "sku": sku,
                "quantity": quantity,
                "idempotency_key": idempotency_key,
                "status": "PENDING",
                "created_at": now,
            }

    def deduct_stock(self, sku_id: int, quantity: int) -> None:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE skus SET available_stock = available_stock - ?, reserved_stock = reserved_stock + ?
                   WHERE id = ?""",
                (quantity, quantity, sku_id),
            )

    def get_reservation(self, reservation_id: int) -> Optional[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT r.id, r.sku_id, s.sku, r.quantity, r.status, r.created_at, r.confirmed_at
                   FROM reservations r
                   JOIN skus s ON r.sku_id = s.id
                   WHERE r.id = ?""",
                (reservation_id,),
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def confirm_reservation(self, reservation_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET status = ?, confirmed_at = ? WHERE id = ?",
                ("CONFIRMED", now, reservation_id),
            )

    def mark_expired(self, reservation_id: int) -> None:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                ("EXPIRED", reservation_id),
            )

    def cancel_reservation(self, reservation_id: int) -> None:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                ("CANCELLED", reservation_id),
            )

    def restore_stock(self, sku_id: int, quantity: int) -> None:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE skus SET available_stock = available_stock + ?, reserved_stock = reserved_stock - ?
                   WHERE id = ?""",
                (quantity, quantity, sku_id),
            )


class OrderRepository:
    def __init__(self, db: Database):
        self.db = db

    def create_order(self, reservation_id: int) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
                (reservation_id, now),
            )
            cursor.execute("SELECT id FROM orders WHERE reservation_id = ?", (reservation_id,))
            row = cursor.fetchone()
            return {"id": row["id"], "reservation_id": reservation_id, "created_at": now}

    def get_orders_paginated(self, page: int, size: int) -> Tuple[List[Dict[str, Any]], int]:
        offset = (page - 1) * size
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM orders")
            total = cursor.fetchone()["count"]

            cursor.execute(
                "SELECT id, reservation_id, created_at FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
                (size, offset),
            )
            rows = cursor.fetchall()
            orders = [dict(row) for row in rows]
            return orders, total
