"""Database repository layer."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

DATABASE_PATH = Path("commerce.db")


def get_db_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the database with required tables."""
    conn = get_db_connection()
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
            sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            status TEXT NOT NULL,
            idempotency_key TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (sku_id) REFERENCES skus(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER NOT NULL,
            sku_id INTEGER NOT NULL,
            sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (reservation_id) REFERENCES reservations(id),
            FOREIGN KEY (sku_id) REFERENCES skus(id)
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

        cursor.execute(
            "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
            (sku, initial_stock),
        )
        conn.commit()
        sku_id = cursor.lastrowid
        conn.close()

        return {"id": sku_id, "sku": sku, "available_stock": initial_stock}

    @staticmethod
    def get_sku_by_id(sku_id: int) -> Optional[dict]:
        """Get a SKU by ID."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, sku, available_stock FROM skus WHERE id = ?", (sku_id,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    @staticmethod
    def get_sku_by_name(sku: str) -> Optional[dict]:
        """Get a SKU by name."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, sku, available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    @staticmethod
    def adjust_stock(sku: str, amount: int) -> Optional[dict]:
        """Adjust stock for a SKU."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
            (amount, sku),
        )
        conn.commit()

        cursor.execute("SELECT id, sku, available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None


class ReservationRepository:
    """Repository for reservation operations."""

    @staticmethod
    def create_reservation(
        sku_id: int,
        sku: str,
        quantity: int,
        idempotency_key: str,
        created_at: datetime,
    ) -> dict:
        """Create a new reservation."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO reservations
            (sku_id, sku, quantity, status, idempotency_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (sku_id, sku, quantity, "PENDING", idempotency_key, created_at.isoformat()),
        )
        conn.commit()
        reservation_id = cursor.lastrowid
        conn.close()

        return {
            "id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "status": "PENDING",
            "created_at": created_at,
        }

    @staticmethod
    def get_reservation_by_id(reservation_id: int) -> Optional[dict]:
        """Get a reservation by ID."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, sku_id, sku, quantity, status, created_at FROM reservations WHERE id = ?",
            (reservation_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            row_dict = dict(row)
            row_dict["created_at"] = datetime.fromisoformat(row_dict["created_at"])
            return row_dict
        return None

    @staticmethod
    def get_reservation_by_idempotency_key(idempotency_key: str) -> Optional[dict]:
        """Get a reservation by idempotency key."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, sku_id, sku, quantity, status, created_at FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            row_dict = dict(row)
            row_dict["created_at"] = datetime.fromisoformat(row_dict["created_at"])
            return row_dict
        return None

    @staticmethod
    def update_reservation_status(reservation_id: int, status: str) -> bool:
        """Update the status of a reservation."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id),
        )
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()

        return success


class OrderRepository:
    """Repository for order operations."""

    @staticmethod
    def create_order(reservation_id: int, sku_id: int, sku: str, quantity: int) -> dict:
        """Create a new order."""
        conn = get_db_connection()
        cursor = conn.cursor()

        created_at = datetime.utcnow()
        cursor.execute(
            """INSERT INTO orders
            (reservation_id, sku_id, sku, quantity, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (reservation_id, sku_id, sku, quantity, created_at.isoformat()),
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()

        return {
            "id": order_id,
            "reservation_id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "created_at": created_at,
        }

    @staticmethod
    def get_orders(page: int = 1, size: int = 10) -> Tuple[list, int]:
        """Get orders with pagination."""
        conn = get_db_connection()
        cursor = conn.cursor()

        offset = (page - 1) * size

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT id, reservation_id, sku, quantity, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (size, offset),
        )
        rows = cursor.fetchall()
        conn.close()

        orders = []
        for row in rows:
            row_dict = dict(row)
            row_dict["created_at"] = datetime.fromisoformat(row_dict["created_at"])
            orders.append(row_dict)

        return orders, total
