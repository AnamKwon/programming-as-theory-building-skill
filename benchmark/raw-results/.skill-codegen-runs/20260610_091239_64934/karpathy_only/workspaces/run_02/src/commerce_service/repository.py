"""Database repository layer."""

import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import uuid


class SKU:
    def __init__(
        self,
        sku_id: str,
        name: str,
        unit_price: Decimal,
        stock_quantity: int,
        created_at: datetime,
    ):
        self.sku_id = sku_id
        self.name = name
        self.unit_price = unit_price
        self.stock_quantity = stock_quantity
        self.created_at = created_at


class Reservation:
    def __init__(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        status: str,
        expires_at: datetime,
        created_at: datetime,
        idempotency_key: str,
    ):
        self.reservation_id = reservation_id
        self.sku_id = sku_id
        self.quantity = quantity
        self.status = status
        self.expires_at = expires_at
        self.created_at = created_at
        self.idempotency_key = idempotency_key


class Order:
    def __init__(
        self,
        order_id: str,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        status: str,
        created_at: datetime,
    ):
        self.order_id = order_id
        self.reservation_id = reservation_id
        self.sku_id = sku_id
        self.quantity = quantity
        self.status = status
        self.created_at = created_at


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
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
                sku_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                unit_price REAL NOT NULL,
                stock_quantity INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                reservation_id TEXT PRIMARY KEY,
                sku_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
            )
        """)

        cursor.execute("""
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

        conn.commit()
        conn.close()

    def create_sku(
        self, sku_id: str, name: str, unit_price: Decimal, stock_quantity: int = 0
    ) -> SKU:
        conn = self._get_connection()
        cursor = conn.cursor()
        created_at = datetime.now()

        cursor.execute(
            """
            INSERT INTO skus (sku_id, name, unit_price, stock_quantity, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sku_id, name, float(unit_price), stock_quantity, created_at.isoformat()),
        )
        conn.commit()
        conn.close()

        return SKU(sku_id, name, unit_price, stock_quantity, created_at)

    def get_sku(self, sku_id: str) -> SKU | None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skus WHERE sku_id = ?", (sku_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return SKU(
            sku_id=row["sku_id"],
            name=row["name"],
            unit_price=Decimal(str(row["unit_price"])),
            stock_quantity=row["stock_quantity"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def update_stock(self, sku_id: str, quantity_delta: int) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE skus SET stock_quantity = stock_quantity + ? WHERE sku_id = ?",
            (quantity_delta, sku_id),
        )
        conn.commit()
        conn.close()

    def create_reservation(
        self,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        expires_in_minutes: int = 10,
    ) -> Reservation:
        reservation_id = str(uuid.uuid4())
        created_at = datetime.now()
        expires_at = created_at + timedelta(minutes=expires_in_minutes)

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO reservations (reservation_id, sku_id, quantity, status, expires_at, created_at, idempotency_key)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reservation_id,
                sku_id,
                quantity,
                "pending",
                expires_at.isoformat(),
                created_at.isoformat(),
                idempotency_key,
            ),
        )
        conn.commit()
        conn.close()

        return Reservation(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status="pending",
            expires_at=expires_at,
            created_at=created_at,
            idempotency_key=idempotency_key,
        )

    def get_reservation(self, reservation_id: str) -> Reservation | None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reservations WHERE reservation_id = ?", (reservation_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return Reservation(
            reservation_id=row["reservation_id"],
            sku_id=row["sku_id"],
            quantity=row["quantity"],
            status=row["status"],
            expires_at=datetime.fromisoformat(row["expires_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            idempotency_key=row["idempotency_key"],
        )

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return Reservation(
            reservation_id=row["reservation_id"],
            sku_id=row["sku_id"],
            quantity=row["quantity"],
            status=row["status"],
            expires_at=datetime.fromisoformat(row["expires_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            idempotency_key=row["idempotency_key"],
        )

    def update_reservation_status(self, reservation_id: str, status: str) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE reservation_id = ?",
            (status, reservation_id),
        )
        conn.commit()
        conn.close()

    def create_order(
        self, reservation_id: str, sku_id: str, quantity: int
    ) -> Order:
        order_id = str(uuid.uuid4())
        created_at = datetime.now()

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO orders (order_id, reservation_id, sku_id, quantity, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                reservation_id,
                sku_id,
                quantity,
                "pending",
                created_at.isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        return Order(
            order_id=order_id,
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status="pending",
            created_at=created_at,
        )

    def get_order(self, order_id: str) -> Order | None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return Order(
            order_id=row["order_id"],
            reservation_id=row["reservation_id"],
            sku_id=row["sku_id"],
            quantity=row["quantity"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def update_order_status(self, order_id: str, status: str) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET status = ? WHERE order_id = ?",
            (status, order_id),
        )
        conn.commit()
        conn.close()

    def list_orders(self, page: int = 1, page_size: int = 20) -> tuple[list[Order], int]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]

        offset = (page - 1) * page_size
        cursor.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        )
        rows = cursor.fetchall()
        conn.close()

        orders = [
            Order(
                order_id=row["order_id"],
                reservation_id=row["reservation_id"],
                sku_id=row["sku_id"],
                quantity=row["quantity"],
                status=row["status"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

        return orders, total
