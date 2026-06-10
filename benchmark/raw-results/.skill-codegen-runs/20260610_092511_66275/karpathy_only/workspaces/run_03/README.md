# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Features

- SKU and stock management
- Reservation lifecycle (create, confirm, cancel)
- Order lookup with pagination
- Idempotent API operations
- Reservation expiration handling
- API key authentication for mutations

## Running

```bash
pip install -e .[dev]
uvicorn commerce_service.app:app --reload
```

## Testing

```bash
pytest
```

## API Endpoints

### Health
- `GET /health` - Service health check

### SKU Management
- `POST /skus` - Create a SKU (requires API key)
- `POST /stock/adjust` - Adjust stock level (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination (query params: `skip`, `limit`)

## Configuration

Set `API_KEY` environment variable for authentication.
