import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import DBOrder, DBReservation, DBSku, DBStock, OrderState, ReservationState


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock (
                    sku_id INTEGER PRIMARY KEY,
                    available INTEGER NOT NULL DEFAULT 0,
                    reserved INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(sku_id) REFERENCES skus(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(sku_id) REFERENCES skus(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(sku_id) REFERENCES skus(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    key TEXT PRIMARY KEY,
                    reservation_id INTEGER NOT NULL,
                    FOREIGN KEY(reservation_id) REFERENCES reservations(id)
                )
            """)

            conn.commit()

    def create_sku(self, sku: str, name: str, price: float) -> DBSku:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                "INSERT INTO skus (sku, name, price, created_at) VALUES (?, ?, ?, ?)",
                (sku, name, price, now),
            )
            sku_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO stock (sku_id, available, reserved) VALUES (?, ?, ?)",
                (sku_id, 0, 0),
            )
            conn.commit()

        return DBSku(sku_id, sku, name, price, datetime.fromisoformat(now))

    def get_sku(self, sku_id: int) -> Optional[DBSku]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, sku, name, price, created_at FROM skus WHERE id = ?", (sku_id,))
            row = cursor.fetchone()

        if not row:
            return None
        return DBSku(row[0], row[1], row[2], row[3], datetime.fromisoformat(row[4]))

    def get_stock(self, sku_id: int) -> Optional[DBStock]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sku_id, available, reserved FROM stock WHERE sku_id = ?",
                (sku_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None
        return DBStock(row[0], row[1], row[2])

    def adjust_stock(self, sku_id: int, quantity: int) -> Optional[DBStock]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT available FROM stock WHERE sku_id = ?", (sku_id,))
            row = cursor.fetchone()
            if not row:
                return None

            new_available = row[0] + quantity
            cursor.execute(
                "UPDATE stock SET available = ? WHERE sku_id = ?",
                (new_available, sku_id),
            )
            conn.commit()

        return self.get_stock(sku_id)

    def check_idempotency_key(self, key: str) -> Optional[int]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT reservation_id FROM idempotency_keys WHERE key = ?", (key,))
            row = cursor.fetchone()

        return row[0] if row else None

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        expires_at: datetime,
        idempotency_key: str,
    ) -> DBReservation:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()

            cursor.execute(
                "INSERT INTO reservations (sku_id, quantity, state, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
                (sku_id, quantity, ReservationState.PENDING, expires_at.isoformat(), now),
            )
            reservation_id = cursor.lastrowid

            cursor.execute(
                "INSERT INTO idempotency_keys (key, reservation_id) VALUES (?, ?)",
                (idempotency_key, reservation_id),
            )

            cursor.execute(
                "UPDATE stock SET available = available - ?, reserved = reserved + ? WHERE sku_id = ?",
                (quantity, quantity, sku_id),
            )

            conn.commit()

        return DBReservation(
            reservation_id,
            sku_id,
            quantity,
            ReservationState.PENDING,
            expires_at,
            datetime.fromisoformat(now),
        )

    def get_reservation(self, reservation_id: int) -> Optional[DBReservation]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, sku_id, quantity, state, expires_at, created_at FROM reservations WHERE id = ?",
                (reservation_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None
        return DBReservation(
            row[0],
            row[1],
            row[2],
            ReservationState(row[3]),
            datetime.fromisoformat(row[4]),
            datetime.fromisoformat(row[5]),
        )

    def confirm_reservation(self, reservation_id: int) -> Optional[DBReservation]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET state = ? WHERE id = ?",
                (ReservationState.CONFIRMED, reservation_id),
            )
            conn.commit()

        return self.get_reservation(reservation_id)

    def cancel_reservation(self, reservation_id: int) -> Optional[DBReservation]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT quantity, sku_id FROM reservations WHERE id = ?",
                (reservation_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            quantity, sku_id = row
            cursor.execute(
                "UPDATE reservations SET state = ? WHERE id = ?",
                (ReservationState.CANCELLED, reservation_id),
            )
            cursor.execute(
                "UPDATE stock SET available = available + ?, reserved = reserved - ? WHERE sku_id = ?",
                (quantity, quantity, sku_id),
            )
            conn.commit()

        return self.get_reservation(reservation_id)

    def create_order(self, sku_id: int, quantity: int, state: OrderState = OrderState.RESERVED) -> DBOrder:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                "INSERT INTO orders (sku_id, quantity, state, created_at) VALUES (?, ?, ?, ?)",
                (sku_id, quantity, state, now),
            )
            order_id = cursor.lastrowid
            conn.commit()

        return DBOrder(order_id, sku_id, quantity, state, datetime.fromisoformat(now))

    def get_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[DBOrder], int]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM orders")
            total = cursor.fetchone()[0]

            cursor.execute(
                "SELECT id, sku_id, quantity, state, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = cursor.fetchall()

        orders = [
            DBOrder(row[0], row[1], row[2], OrderState(row[3]), datetime.fromisoformat(row[4]))
            for row in rows
        ]
        return orders, total

    def expire_reservations(self) -> int:
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """SELECT id, quantity, sku_id FROM reservations
                   WHERE state = ? AND expires_at <= ?""",
                (ReservationState.PENDING, now),
            )
            expired = cursor.fetchall()

            for reservation_id, quantity, sku_id in expired:
                cursor.execute(
                    "UPDATE reservations SET state = ? WHERE id = ?",
                    (ReservationState.EXPIRED, reservation_id),
                )
                cursor.execute(
                    "UPDATE stock SET available = available + ?, reserved = reserved - ? WHERE sku_id = ?",
                    (quantity, quantity, sku_id),
                )

            conn.commit()

        return len(expired)
