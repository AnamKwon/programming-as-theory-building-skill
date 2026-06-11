# Commerce Inventory & Order API

A FastAPI-based service for managing inventory, reservations, and orders with token-based authentication.

## Features

- SKU inventory management
- Stock adjustment
- Reservation system with idempotency and expiration
- Order management with pagination
- Token-based API authentication
- SQLite persistence

## Setup

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running the Server

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`

## Running Tests

```bash
pytest
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create SKU
- `POST /stock/adjust` - Adjust stock level
- `POST /reservations` - Create reservation
- `POST /reservations/{id}/confirm` - Confirm reservation
- `POST /reservations/{id}/cancel` - Cancel reservation
- `GET /orders` - List orders with pagination

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header. The default API key is `test-key-123`.
