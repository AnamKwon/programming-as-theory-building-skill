# Commerce Inventory & Order API

A FastAPI-based service for managing inventory SKUs, reservations, and orders with idempotency and expiration handling.

## Features

- SKU management with stock tracking
- Reservation system with idempotent retries
- Stock adjustment and validation
- Order confirmation with expiration checks
- Pagination support
- API token-based authentication for mutations

## Requirements

- Python 3.11+
- FastAPI 0.104.1
- Pydantic 2.5.0
- SQLAlchemy 2.0.23

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running the Server

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

## Running Tests

```bash
pytest tests/
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create SKU with initial stock
- `POST /stock/adjust` - Adjust stock level
- `POST /reservations` - Create reservation (with idempotency)
- `POST /reservations/{id}/confirm` - Confirm reservation
- `POST /reservations/{id}/cancel` - Cancel reservation
- `GET /orders` - List orders with pagination

## Authentication

Mutating endpoints (POST, PUT, DELETE) require an API token via the `X-API-Key` header.

Default token: `test-key-123`
