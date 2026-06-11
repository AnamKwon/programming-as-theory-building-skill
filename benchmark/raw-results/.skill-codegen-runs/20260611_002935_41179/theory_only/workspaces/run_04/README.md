# Commerce Inventory & Order API

A FastAPI-based inventory and order management service with support for stock reservations, idempotent operations, and reservation expiration.

## Features

- SKU management with stock tracking
- Stock adjustment operations
- Reservation system with idempotency keys
- Reservation lifecycle (PENDING → CONFIRMED or CANCELLED)
- Reservation expiration (300 seconds)
- Order tracking with pagination
- API token authentication for mutations

## Getting Started

### Installation

```bash
pip install -e ".[dev]"
```

### Running the Server

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Running Tests

```bash
pytest
```

## API Endpoints

### Health Check
- `GET /health` - Returns service health status (no auth required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock

### Stock Operations
- `POST /stock/adjust` - Adjust stock level for a SKU

### Reservations
- `POST /reservations` - Create a reservation with idempotency
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a pending reservation

### Orders
- `GET /orders` - List orders with pagination

## Authentication

All mutating endpoints require an `X-API-Key` header with a valid API token.
The default token is `test-api-key-12345`.

## Database

The service uses SQLite for data persistence. The database file is created automatically on first run.
