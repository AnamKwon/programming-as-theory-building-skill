import sqlite3
from datetime import datetime
from pathlib import Path


class Repository:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                available_stock INTEGER NOT NULL,
                reserved_stock INTEGER NOT NULL DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                idempotency_key TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            )
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO skus (sku, available_stock, reserved_stock) VALUES (?, ?, ?)",
            (sku, initial_stock, 0)
        )
        conn.commit()
        sku_id = cursor.lastrowid
        conn.close()
        return {
            "id": sku_id,
            "sku": sku,
            "available_stock": initial_stock,
            "reserved_stock": 0
        }

    def get_sku_by_name(self, sku: str) -> dict | None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, sku, available_stock, reserved_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    def adjust_stock(self, sku: str, amount: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, available_stock, reserved_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise ValueError(f"SKU {sku} not found")

        new_available = row["available_stock"] + amount
        cursor.execute("UPDATE skus SET available_stock = ? WHERE sku = ?", (new_available, sku))
        conn.commit()
        conn.close()
        return {
            "sku": sku,
            "available_stock": new_available,
            "reserved_stock": row["reserved_stock"]
        }

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, available_stock, reserved_stock FROM skus WHERE sku = ?", (sku,))
        sku_row = cursor.fetchone()
        if not sku_row:
            conn.close()
            raise ValueError(f"SKU {sku} not found")

        if sku_row["available_stock"] < quantity:
            conn.close()
            raise ValueError("Insufficient stock")

        now = datetime.utcnow()
        cursor.execute(
            """INSERT INTO reservations (sku_id, sku, quantity, status, idempotency_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sku_row["id"], sku, quantity, "PENDING", idempotency_key, now)
        )
        conn.commit()
        reservation_id = cursor.lastrowid

        new_available = sku_row["available_stock"] - quantity
        new_reserved = sku_row["reserved_stock"] + quantity
        cursor.execute(
            "UPDATE skus SET available_stock = ?, reserved_stock = ? WHERE id = ?",
            (new_available, new_reserved, sku_row["id"])
        )
        conn.commit()
        conn.close()

        return {
            "id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "status": "PENDING",
            "idempotency_key": idempotency_key,
            "created_at": now
        }

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, status, idempotency_key, created_at FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    def get_reservation_by_id(self, reservation_id: int) -> dict | None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, status, idempotency_key, created_at FROM reservations WHERE id = ?",
            (reservation_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    def confirm_reservation(self, reservation_id: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT sku, quantity, status FROM reservations WHERE id = ?",
            (reservation_id,)
        )
        res_row = cursor.fetchone()
        if not res_row:
            conn.close()
            raise ValueError("Reservation not found")

        if res_row["status"] != "PENDING":
            conn.close()
            raise ValueError(f"Reservation is not PENDING")

        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            ("CONFIRMED", reservation_id)
        )

        now = datetime.utcnow()
        cursor.execute(
            "INSERT INTO orders (reservation_id, sku, quantity, created_at) VALUES (?, ?, ?, ?)",
            (reservation_id, res_row["sku"], res_row["quantity"], now)
        )
        conn.commit()

        order_id = cursor.lastrowid
        conn.close()

        return {
            "id": order_id,
            "reservation_id": reservation_id,
            "sku": res_row["sku"],
            "quantity": res_row["quantity"],
            "created_at": now
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT sku, quantity, status FROM reservations WHERE id = ?",
            (reservation_id,)
        )
        res_row = cursor.fetchone()
        if not res_row:
            conn.close()
            raise ValueError("Reservation not found")

        if res_row["status"] != "PENDING":
            conn.close()
            raise ValueError(f"Reservation is not PENDING")

        cursor.execute("UPDATE reservations SET status = ? WHERE id = ?", ("CANCELLED", reservation_id))

        cursor.execute("SELECT id, available_stock, reserved_stock FROM skus WHERE sku = ?", (res_row["sku"],))
        sku_row = cursor.fetchone()

        new_available = sku_row["available_stock"] + res_row["quantity"]
        new_reserved = sku_row["reserved_stock"] - res_row["quantity"]
        cursor.execute(
            "UPDATE skus SET available_stock = ?, reserved_stock = ? WHERE id = ?",
            (new_available, new_reserved, sku_row["id"])
        )
        conn.commit()
        conn.close()

        return {
            "sku": res_row["sku"],
            "quantity": res_row["quantity"],
            "status": "CANCELLED"
        }

    def mark_reservation_expired(self, reservation_id: int):
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT sku, quantity FROM reservations WHERE id = ?",
            (reservation_id,)
        )
        res_row = cursor.fetchone()

        cursor.execute("UPDATE reservations SET status = ? WHERE id = ?", ("EXPIRED", reservation_id))

        cursor.execute("SELECT id, available_stock, reserved_stock FROM skus WHERE sku = ?", (res_row["sku"],))
        sku_row = cursor.fetchone()

        new_available = sku_row["available_stock"] + res_row["quantity"]
        new_reserved = sku_row["reserved_stock"] - res_row["quantity"]
        cursor.execute(
            "UPDATE skus SET available_stock = ?, reserved_stock = ? WHERE id = ?",
            (new_available, new_reserved, sku_row["id"])
        )
        conn.commit()
        conn.close()

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]

        offset = (page - 1) * size
        cursor.execute(
            "SELECT id, reservation_id, sku, quantity, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (size, offset)
        )
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows], total
