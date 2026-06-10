# Commerce Inventory & Order API

A FastAPI-based service for managing SKU inventory, stock reservations, and order processing with idempotency guarantees.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Adjust inventory levels for SKUs
- **Reservations**: Reserve stock with idempotency support and expiration rules
- **Order Processing**: Convert confirmed reservations into orders
- **Pagination**: Browse orders with configurable pagination
- **API Security**: Token-based authentication for all mutations

## Running

Install dependencies:
```bash
pip install -e ".[dev]"
```

Start the server:
```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

## Testing

Run the test suite:
```bash
pytest tests/
```

## API Endpoints

### Health Check
- `GET /health` - Returns {"status": "ok"}

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock level for a SKU

### Reservations
- `POST /reservations` - Create a reservation (idempotent)
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a pending reservation

### Orders
- `GET /orders` - List orders with pagination

## Configuration

Set the API token via the `X-API-Key` header for all mutating endpoints. The default token is "test-token-123" for local testing.
