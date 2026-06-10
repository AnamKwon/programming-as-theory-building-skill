# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Features

- SKU management and stock tracking
- Reservation creation with stock availability checks
- Idempotent reservation operations via idempotency keys
- Automatic reservation expiration (30 minutes)
- Order state transitions and tracking
- Pagination for order lookups
- API key authentication for mutations
- SQLite persistence

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Run the API

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Run Tests

```bash
pytest
```

## API Endpoints

### Health Check
- `GET /health` - Service health status

### SKU Management
- `POST /skus` - Create a new SKU
- `POST /skus/{sku_id}/adjust-stock` - Adjust stock quantity

### Reservations
- `POST /reservations` - Create a reservation
- `POST /reservations/{reservation_id}/confirm` - Confirm a pending reservation
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - List orders with pagination

## Authentication

Mutating endpoints require an `X-API-Key` header. Default key is `test-key-123`.

## Database

The service uses SQLite (default: `commerce.db`). Database is automatically initialized on startup.
