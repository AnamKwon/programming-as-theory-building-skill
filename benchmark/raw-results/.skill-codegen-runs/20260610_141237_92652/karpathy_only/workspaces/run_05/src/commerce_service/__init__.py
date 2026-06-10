import sqlite3
import os
from pathlib import Path

DB_PATH = os.getenv("DB_PATH", ":memory:")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skus (
            sku TEXT PRIMARY KEY,
            stock INTEGER NOT NULL DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at REAL NOT NULL,
            idempotency_key TEXT UNIQUE,
            FOREIGN KEY (sku) REFERENCES skus(sku)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER NOT NULL UNIQUE,
            created_at REAL NOT NULL,
            FOREIGN KEY (reservation_id) REFERENCES reservations(id)
        )
    """)

    conn.commit()
    conn.close()

__all__ = ["init_db"]
