import sqlite3
from datetime import datetime
from typing import Optional, Tuple, List
import os


DB_PATH = "commerce.db"


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE NOT NULL,
            stock INTEGER NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            status TEXT NOT NULL,
            idempotency_key TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(sku) REFERENCES skus(sku)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY(reservation_id) REFERENCES reservations(id)
        )
    """)

    conn.commit()
    conn.close()


class SKURepository:
    @staticmethod
    def create_sku(sku: str, initial_stock: int) -> dict:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO skus (sku, stock) VALUES (?, ?)",
            (sku, initial_stock)
        )
        conn.commit()
        sku_id = cursor.lastrowid
        conn.close()
        return {"id": sku_id, "sku": sku, "stock": initial_stock}

    @staticmethod
    def get_sku_by_name(sku: str) -> Optional[dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, sku, stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    @staticmethod
    def adjust_stock(sku: str, amount: int) -> dict:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE skus SET stock = stock + ? WHERE sku = ?",
            (amount, sku)
        )
        conn.commit()
        cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()
        return {"sku": sku, "stock": row[0]}

    @staticmethod
    def get_stock(sku: str) -> Optional[int]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0]
        return None


class ReservationRepository:
    @staticmethod
    def check_idempotency_key(idempotency_key: str) -> Optional[dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, status, idempotency_key, created_at FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "id": row[0],
                "sku": row[1],
                "quantity": row[2],
                "status": row[3],
                "idempotency_key": row[4],
                "created_at": row[5]
            }
        return None

    @staticmethod
    def create_reservation(
        sku: str,
        quantity: int,
        idempotency_key: str,
        created_at: str
    ) -> dict:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO reservations (sku, quantity, status, idempotency_key, created_at) VALUES (?, ?, ?, ?, ?)",
            (sku, quantity, "PENDING", idempotency_key, created_at)
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
            "created_at": created_at
        }

    @staticmethod
    def get_reservation(reservation_id: int) -> Optional[dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, status, idempotency_key, created_at FROM reservations WHERE id = ?",
            (reservation_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "id": row[0],
                "sku": row[1],
                "quantity": row[2],
                "status": row[3],
                "idempotency_key": row[4],
                "created_at": row[5]
            }
        return None

    @staticmethod
    def update_reservation_status(reservation_id: int, status: str) -> dict:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id)
        )
        conn.commit()
        cursor.execute(
            "SELECT id, sku, quantity, status, idempotency_key, created_at FROM reservations WHERE id = ?",
            (reservation_id,)
        )
        row = cursor.fetchone()
        conn.close()
        return {
            "id": row[0],
            "sku": row[1],
            "quantity": row[2],
            "status": row[3],
            "idempotency_key": row[4],
            "created_at": row[5]
        }


class OrderRepository:
    @staticmethod
    def create_order(reservation_id: int, created_at: str) -> dict:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
            (reservation_id, created_at)
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()
        return {
            "id": order_id,
            "reservation_id": reservation_id,
            "created_at": created_at
        }

    @staticmethod
    def get_orders_paginated(page: int, size: int) -> Tuple[List[dict], int]:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM orders")
        total = cursor.fetchone()[0]

        offset = (page - 1) * size
        cursor.execute(
            "SELECT id, reservation_id, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (size, offset)
        )
        rows = cursor.fetchall()
        conn.close()

        orders = [
            {
                "id": row[0],
                "reservation_id": row[1],
                "created_at": row[2]
            }
            for row in rows
        ]
        return orders, total
