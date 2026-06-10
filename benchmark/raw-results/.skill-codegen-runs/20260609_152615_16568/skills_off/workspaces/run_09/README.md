# Commerce Service

An inventory reservation and order orchestration API for small commerce backends.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Track and adjust available and reserved inventory
- **Reservation System**: Reserve inventory with idempotency, expiration, and state transitions
- **Order Orchestration**: Confirm reservations into orders with full audit trail
- **Pagination**: List orders with cursor-based pagination
- **API Key Security**: Protect mutating endpoints with API key authentication

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run the service
uvicorn commerce_service.app:app --reload

# Run tests
pytest tests/
```

## API Overview

### Health Check
- `GET /health` - Service health check

### SKU Management
- `POST /skus` - Create a new SKU
- `POST /skus/{sku_id}/stock` - Adjust stock levels

### Reservations
- `POST /reservations` - Create a reservation with idempotency
- `POST /reservations/{reservation_id}/confirm` - Confirm a pending reservation
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - List confirmed orders with pagination

## Authentication

Mutating endpoints require an `X-API-Key` header. Set the key via the `API_KEY` environment variable.

## Database

Uses SQLite with file-based persistence. Database schema is created on startup.

## Service Design

- **Repository Layer**: Data access abstraction for SKUs, reservations, and orders
- **Service Layer**: Business logic for inventory, reservations, and order orchestration
- **API Layer**: FastAPI endpoints with request validation and error handling
- **Security Layer**: API key validation for protected endpoints
