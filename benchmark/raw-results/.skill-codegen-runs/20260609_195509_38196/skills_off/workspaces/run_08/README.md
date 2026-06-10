# Commerce Service

Inventory reservation and order orchestration API built with FastAPI.

## Features

- **Health Checks**: Monitor service availability
- **SKU Management**: Create and manage product SKUs
- **Inventory Management**: Track stock and reservations
- **Reservation System**: Reserve inventory with automatic expiration
- **Order Management**: Confirm and cancel orders with pagination support
- **Idempotency**: Built-in idempotency key support for safe retries
- **API Key Security**: Protected mutation endpoints

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run the service
uvicorn src.commerce_service.app:app --reload

# Run tests
pytest
```

## API Endpoints

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a new SKU (requires API key)

### Inventory
- `PATCH /inventory/{sku_id}` - Adjust stock quantity (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination (requires API key)

## Configuration

Set the `API_KEY` environment variable for authentication:

```bash
API_KEY=your-secret-key uvicorn src.commerce_service.app:app
```

Default API key for development: `dev-key-12345`

## Database

The service uses SQLite with auto-migration on startup. The database file is created at `commerce.db` in the current directory.

## Reservation Lifecycle

1. Create a reservation - reserves inventory for 5 minutes
2. Confirm the reservation - converts to a fulfilled order
3. (Optional) Cancel - returns inventory to available pool

Expired reservations are automatically cleaned up when accessed.
