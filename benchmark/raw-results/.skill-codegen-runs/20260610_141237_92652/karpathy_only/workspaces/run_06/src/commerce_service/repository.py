import sqlite3
from datetime import datetime
from typing import Optional, Tuple

DATABASE_PATH = "commerce.db"


class SKURecord:
    def __init__(self, id: int, sku: str, available_stock: int, reserved_stock: int, created_at: datetime):
        self.id = id
        self.sku = sku
        self.available_stock = available_stock
        self.reserved_stock = reserved_stock
        self.created_at = created_at


class ReservationRecord:
    def __init__(
        self,
        id: int,
        sku_id: int,
        sku: str,
        quantity: int,
        idempotency_key: str,
        status: str,
        created_at: datetime,
    ):
        self.id = id
        self.sku_id = sku_id
        self.sku = sku
        self.quantity = quantity
        self.idempotency_key = idempotency_key
        self.status = status
        self.created_at = created_at


class OrderRecord:
    def __init__(self, id: int, reservation_id: int, created_at: datetime):
        self.id = id
        self.reservation_id = reservation_id
        self.created_at = created_at


class Repository:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                available_stock INTEGER NOT NULL,
                reserved_stock INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus (id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations (id)
            )
            """
        )

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> SKURecord:
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.utcnow().isoformat()
        cursor.execute(
            "INSERT INTO skus (sku, available_stock, reserved_stock, created_at) VALUES (?, ?, ?, ?)",
            (sku, initial_stock, 0, now),
        )
        conn.commit()

        sku_id = cursor.lastrowid
        conn.close()

        return SKURecord(sku_id, sku, initial_stock, 0, datetime.fromisoformat(now))

    def get_sku(self, sku: str) -> Optional[SKURecord]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, sku, available_stock, reserved_stock, created_at FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return SKURecord(
            id=row["id"],
            sku=row["sku"],
            available_stock=row["available_stock"],
            reserved_stock=row["reserved_stock"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def adjust_stock(self, sku: str, amount: int) -> Optional[int]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return None

        new_stock = row["available_stock"] + amount
        cursor.execute("UPDATE skus SET available_stock = ? WHERE sku = ?", (new_stock, sku))
        conn.commit()
        conn.close()

        return new_stock

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> Tuple[ReservationRecord, bool]:
        conn = self._get_connection()
        cursor = conn.cursor()

        # Check if idempotency key exists
        cursor.execute("SELECT id, sku_id, quantity, status, created_at FROM reservations WHERE idempotency_key = ?", (idempotency_key,))
        existing = cursor.fetchone()

        if existing:
            sku_record = self.get_sku(sku)
            conn.close()
            return (
                ReservationRecord(
                    id=existing["id"],
                    sku_id=existing["sku_id"],
                    sku=sku,
                    quantity=existing["quantity"],
                    idempotency_key=idempotency_key,
                    status=existing["status"],
                    created_at=datetime.fromisoformat(existing["created_at"]),
                ),
                True,
            )

        # Get SKU and check stock
        cursor.execute("SELECT id, available_stock, reserved_stock FROM skus WHERE sku = ?", (sku,))
        sku_row = cursor.fetchone()

        if not sku_row:
            conn.close()
            return None, False

        if sku_row["available_stock"] < quantity:
            conn.close()
            return None, False

        # Deduct stock and create reservation
        new_available = sku_row["available_stock"] - quantity
        new_reserved = sku_row["reserved_stock"] + quantity

        cursor.execute(
            "UPDATE skus SET available_stock = ?, reserved_stock = ? WHERE id = ?",
            (new_available, new_reserved, sku_row["id"]),
        )

        now = datetime.utcnow().isoformat()
        cursor.execute(
            "INSERT INTO reservations (sku_id, quantity, idempotency_key, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (sku_row["id"], quantity, idempotency_key, "PENDING", now),
        )
        conn.commit()

        reservation_id = cursor.lastrowid
        conn.close()

        return (
            ReservationRecord(
                id=reservation_id,
                sku_id=sku_row["id"],
                sku=sku,
                quantity=quantity,
                idempotency_key=idempotency_key,
                status="PENDING",
                created_at=datetime.fromisoformat(now),
            ),
            False,
        )

    def get_reservation(self, reservation_id: int) -> Optional[ReservationRecord]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT r.id, r.sku_id, s.sku, r.quantity, r.idempotency_key, r.status, r.created_at
            FROM reservations r
            JOIN skus s ON r.sku_id = s.id
            WHERE r.id = ?
            """,
            (reservation_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return ReservationRecord(
            id=row["id"],
            sku_id=row["sku_id"],
            sku=row["sku"],
            quantity=row["quantity"],
            idempotency_key=row["idempotency_key"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def update_reservation_status(self, reservation_id: int, new_status: str) -> Optional[ReservationRecord]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("UPDATE reservations SET status = ? WHERE id = ?", (new_status, reservation_id))
        conn.commit()
        conn.close()

        return self.get_reservation(reservation_id)

    def create_order(self, reservation_id: int) -> OrderRecord:
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.utcnow().isoformat()
        cursor.execute(
            "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
            (reservation_id, now),
        )
        conn.commit()

        order_id = cursor.lastrowid
        conn.close()

        return OrderRecord(order_id, reservation_id, datetime.fromisoformat(now))

    def restore_stock(self, reservation_id: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT sku_id, quantity FROM reservations WHERE id = ?", (reservation_id,))
        res_row = cursor.fetchone()

        if not res_row:
            conn.close()
            return False

        sku_id = res_row["sku_id"]
        quantity = res_row["quantity"]

        cursor.execute(
            "SELECT available_stock, reserved_stock FROM skus WHERE id = ?",
            (sku_id,),
        )
        sku_row = cursor.fetchone()

        new_available = sku_row["available_stock"] + quantity
        new_reserved = sku_row["reserved_stock"] - quantity

        cursor.execute(
            "UPDATE skus SET available_stock = ?, reserved_stock = ? WHERE id = ?",
            (new_available, new_reserved, sku_id),
        )
        conn.commit()
        conn.close()

        return True

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[list[OrderRecord], int]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as total FROM orders")
        total = cursor.fetchone()["total"]

        offset = (page - 1) * size
        cursor.execute(
            "SELECT id, reservation_id, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (size, offset),
        )
        rows = cursor.fetchall()
        conn.close()

        orders = [
            OrderRecord(
                id=row["id"],
                reservation_id=row["reservation_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

        return orders, total
