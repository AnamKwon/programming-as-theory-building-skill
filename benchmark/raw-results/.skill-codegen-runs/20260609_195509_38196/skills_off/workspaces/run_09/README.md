# Commerce Service

A FastAPI-based inventory reservation and order orchestration backend for small commerce platforms.

## Features

- SKU and inventory management
- Reservation system with expiration and idempotency
- Order orchestration with state machine
- Pagination for order lookup
- API-key authentication for mutations
- SQLite persistence

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Run

```bash
python -m uvicorn src.commerce_service.app:app --reload
```

Server starts at `http://localhost:8000`.

### Test

```bash
pytest
```

## API Endpoints

- `GET /health` — Health check
- `POST /skus` — Create a SKU (requires API key)
- `POST /skus/{sku_id}/stock` — Adjust stock (requires API key)
- `POST /reservations` — Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` — Confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` — Cancel reservation (requires API key)
- `GET /orders` — List orders with pagination

## API Key

Pass the API key via `X-API-Key` header for mutating endpoints.

## Architecture

- **models.py** — SQLAlchemy ORM and Pydantic schemas
- **repository.py** — Data access layer (SQLite via SQLAlchemy)
- **service.py** — Business logic and invariants
- **security.py** — API key dependency
- **app.py** — FastAPI application and routes
