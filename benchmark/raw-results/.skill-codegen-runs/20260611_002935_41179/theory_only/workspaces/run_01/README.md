# Commerce Inventory & Order API

A FastAPI-based inventory management and order processing service with reservation support, stock management, and idempotent operations.

## Features

- SKU inventory management
- Stock adjustments (positive/negative)
- Reservation system with idempotency
- Automatic expiration of stale reservations
- Order confirmation and cancellation
- Paginated order listing
- API key-based authentication for mutations

## Running the Service

```bash
# Install dependencies
pip install -e ".[dev]"

# Start the server
uvicorn src.commerce_service.app:app --reload

# Run tests
pytest tests/ -v
```

## API Endpoints

### Health Check
- `GET /health` - Health status (no auth required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock levels

### Reservations
- `POST /reservations` - Reserve quantity with idempotency
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - List orders with pagination

## Authentication

All mutation endpoints require an `X-API-Key` header. Default key is `test-key-123`.

## Database

SQLite database file is created at `commerce.db` on first run.
