# Commerce Service

A FastAPI-based inventory reservation and order orchestration service.

## Features

- **SKU Management**: Create and adjust inventory
- **Reservations**: Hold inventory with automatic expiration
- **Idempotency**: Prevent duplicate operations with idempotency keys
- **Order Orchestration**: Confirm reservations into orders
- **API Key Security**: Authenticate mutations with API keys
- **Pagination**: Browse orders with cursor-based pagination

## Quick Start

### Install dependencies
```bash
pip install -e ".[dev]"
```

### Run the service
```bash
uvicorn commerce_service.app:app --reload
```

Service will be available at `http://localhost:8000`.

### Run tests
```bash
pytest
```

## API Endpoints

### Health
- `GET /health` — Service health check

### SKU Management
- `POST /skus` — Create a new SKU (requires API key)
- `PATCH /skus/{sku_id}/stock` — Adjust stock (requires API key)

### Reservations
- `POST /reservations` — Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` — Confirm a reservation to an order (requires API key)
- `DELETE /reservations/{reservation_id}` — Cancel a reservation (requires API key)

### Orders
- `GET /orders` — List orders with pagination (requires API key)
- `GET /orders/{order_id}` — Get an order (requires API key)

## Configuration

Reservations expire after 300 seconds by default. Pass a custom `api_key` header for mutating endpoints.

## Database

Uses SQLite at `commerce.db`. Schema is created automatically on startup.
