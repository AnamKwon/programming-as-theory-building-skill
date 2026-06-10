# Commerce Inventory & Order API

A FastAPI-based inventory management and order processing system with SQLite backend.

## Features

- SKU and stock management
- Reservation system with idempotency
- Order creation and confirmation
- Automatic stock restoration on cancellation
- Reservation expiration enforcement (300s TTL)
- API token-based authentication
- Paginated order retrieval

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running the Server

```bash
uvicorn src.commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/
```

## API Endpoints

### Health Check
- `GET /health` - Returns API status

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock levels for a SKU

### Reservations
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation and create an order
- `POST /reservations/{id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - List orders with pagination

All mutation endpoints require an `X-API-Token` header with a valid token.

## Database

Uses SQLite with tables for:
- SKUs (stock inventory)
- Reservations (pending/confirmed/cancelled reservations)
- Orders (confirmed orders)
