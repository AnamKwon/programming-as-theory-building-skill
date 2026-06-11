"""Database repository for the commerce service."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path("./commerce.db")


def get_db_connection():
    """Get a database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database schema."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skus (
            sku TEXT PRIMARY KEY,
            available_stock INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            status TEXT NOT NULL,
            idempotency_key TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY (sku) REFERENCES skus(sku)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER NOT NULL UNIQUE,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY (reservation_id) REFERENCES reservations(id)
        )
    """)

    conn.commit()
    conn.close()


class SKURepository:
    """Repository for SKU operations."""

    @staticmethod
    def create_sku(sku: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock."""
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            """
            INSERT INTO skus (sku, available_stock, created_at)
            VALUES (?, ?, ?)
            """,
            (sku, initial_stock, now),
        )
        conn.commit()
        conn.close()

        return {"sku": sku, "available_stock": initial_stock}

    @staticmethod
    def get_sku(sku: str) -> Optional[dict]:
        """Get a SKU by its identifier."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT sku, available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    @staticmethod
    def update_stock(sku: str, amount: int) -> Optional[dict]:
        """Adjust stock level by the given amount."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
            (amount, sku),
        )
        conn.commit()

        cursor.execute("SELECT sku, available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None


class ReservationRepository:
    """Repository for reservation operations."""

    @staticmethod
    def create_reservation(
        sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        """Create a new reservation."""
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            """
            INSERT INTO reservations (sku, quantity, status, idempotency_key, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sku, quantity, "PENDING", idempotency_key, now),
        )
        conn.commit()
        reservation_id = cursor.lastrowid
        conn.close()

        return {
            "id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "status": "PENDING",
            "idempotency_key": idempotency_key,
            "created_at": now,
        }

    @staticmethod
    def get_reservation_by_idempotency_key(
        idempotency_key: str,
    ) -> Optional[dict]:
        """Get a reservation by its idempotency key."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, sku, quantity, status, idempotency_key, created_at
            FROM reservations WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            result = dict(row)
            result["created_at"] = datetime.fromisoformat(result["created_at"])
            return result
        return None

    @staticmethod
    def get_reservation(reservation_id: int) -> Optional[dict]:
        """Get a reservation by its ID."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, sku, quantity, status, idempotency_key, created_at
            FROM reservations WHERE id = ?
            """,
            (reservation_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            result = dict(row)
            result["created_at"] = datetime.fromisoformat(result["created_at"])
            return result
        return None

    @staticmethod
    def update_reservation_status(reservation_id: int, status: str) -> Optional[dict]:
        """Update the status of a reservation."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id),
        )
        conn.commit()

        cursor.execute(
            """
            SELECT id, sku, quantity, status, idempotency_key, created_at
            FROM reservations WHERE id = ?
            """,
            (reservation_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            result = dict(row)
            result["created_at"] = datetime.fromisoformat(result["created_at"])
            return result
        return None


class OrderRepository:
    """Repository for order operations."""

    @staticmethod
    def create_order(reservation_id: int) -> dict:
        """Create a new order from a reservation."""
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            """
            INSERT INTO orders (reservation_id, created_at)
            VALUES (?, ?)
            """,
            (reservation_id, now),
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()

        return {
            "id": order_id,
            "reservation_id": reservation_id,
            "created_at": now,
        }

    @staticmethod
    def get_orders(page: int = 1, size: int = 10) -> dict:
        """Get paginated orders."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]

        offset = (page - 1) * size
        cursor.execute(
            """
            SELECT id, reservation_id, created_at FROM orders
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (size, offset),
        )
        rows = cursor.fetchall()
        conn.close()

        orders = []
        for row in rows:
            order = dict(row)
            order["created_at"] = datetime.fromisoformat(order["created_at"])
            orders.append(order)

        total_pages = (total + size - 1) // size
        return {
            "orders": orders,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": total_pages,
        }
