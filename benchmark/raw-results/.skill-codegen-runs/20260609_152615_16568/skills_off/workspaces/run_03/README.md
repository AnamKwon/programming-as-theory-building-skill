# Commerce Service

A FastAPI-based inventory reservation and order orchestration API.

## Features

- **SKU Management**: Create and manage product inventory
- **Reservation System**: Reserve stock with expiration and idempotency
- **Order Orchestration**: Confirm reservations into orders with state tracking
- **API Key Security**: Protect mutating endpoints
- **Pagination**: Support for listing orders with cursor-based pagination

## Quick Start

### Install

```bash
pip install -e ".[dev]"
```

### Run

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`. View the Swagger UI at `/docs`.

### Test

```bash
pytest
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create a SKU (requires API key)
- `POST /skus/{sku}/adjust-stock` - Adjust inventory (requires API key)
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)
- `GET /orders` - List orders with pagination (requires API key)
- `GET /orders/{order_id}` - Get order details (requires API key)

## Authentication

Pass the API key via the `X-API-Key` header. The default test key is `test-api-key-123`.

## Database

Uses SQLite with automatic schema initialization. Database file is created at `./commerce.db`.
