# Commerce Service

An inventory reservation and order orchestration API for small commerce backends.

## Features

- **SKU Management**: Create and manage product catalog
- **Stock Tracking**: Adjust inventory levels with reserved/available accounting
- **Reservations**: Temporary allocation of inventory with automatic expiration
- **Order Confirmation**: Transition reserved orders to confirmed state
- **API Key Authentication**: Protect mutation endpoints with API keys
- **Pagination**: Browse orders with configurable page size
- **Idempotency**: Replay requests safely with idempotency keys

## Running

Install dependencies:
```bash
pip install -e ".[dev]"
```

Run the server:
```bash
uvicorn src.commerce_service.app:app --reload
```

Run tests:
```bash
pytest tests/
```

## API Overview

- `GET /health` - Health check
- `POST /skus` - Create a SKU
- `POST /stock/{sku_id}/adjust` - Adjust inventory
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm reservation to order
- `POST /reservations/{id}/cancel` - Cancel reservation
- `GET /orders?page=1&page_size=10` - List orders with pagination

All mutation endpoints require an `X-API-Key` header.
