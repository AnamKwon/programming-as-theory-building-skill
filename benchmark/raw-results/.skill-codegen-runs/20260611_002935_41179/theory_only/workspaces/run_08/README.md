# Commerce Inventory & Order API

A FastAPI-based service for managing inventory SKUs, stock adjustments, and order reservations with idempotency and expiration logic.

## Features

- **SKU Management**: Create and track stock keeping units with stock levels
- **Stock Adjustments**: Adjust inventory by positive or negative amounts
- **Reservation System**: Reserve stock with idempotent request handling
- **Reservation Lifecycle**: PENDING → CONFIRMED → Order, with automatic cancellation support
- **Expiration Enforcement**: Reservations expire after 300 seconds if not confirmed
- **Pagination**: Retrieve orders with pagination support
- **API Token Security**: All mutations require valid API token authentication

## Quick Start

### Installation

```bash
pip install -e .[dev]
```

### Running the API

```bash
uvicorn commerce_service.app:app --reload
```

### Running Tests

```bash
pytest
```

## API Endpoints

### Health Check
- `GET /health` - Health check endpoint (no auth required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock level for a SKU

### Reservations
- `POST /reservations` - Create a new reservation (idempotent)
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a pending reservation

### Orders
- `GET /orders` - Get paginated list of orders

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Token` header with a valid API token.

Default token: `test-token-12345`

## Database

Uses SQLite with in-memory or file-based storage. Schema is auto-initialized on startup.
