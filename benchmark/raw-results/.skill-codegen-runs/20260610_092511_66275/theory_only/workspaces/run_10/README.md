# Commerce Service

A FastAPI-based inventory reservation and order orchestration service with SQLite backend.

## Features

- **Health checks**: Service liveness endpoint
- **SKU management**: Create and manage product SKUs
- **Stock management**: Adjust available inventory
- **Reservations**: Create, confirm, and cancel stock reservations with idempotency support
- **Orders**: Query order state with pagination
- **Security**: API-key authentication for mutations
- **Business rules**: Stock validation, reservation expiration, proper state transitions

## Setup

Install dependencies:
```bash
pip install -e ".[dev]"
```

## Running

Start the development server:
```bash
python -m uvicorn src.commerce_service.app:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

## Testing

Run the test suite:
```bash
pytest
```

## API Endpoints

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create SKU (requires API key)
- `GET /skus/{sku_id}` - Get SKU details

### Inventory
- `POST /inventory/{sku_id}/adjust` - Adjust stock (requires API key)
- `GET /inventory/{sku_id}` - Get inventory state

### Reservations
- `POST /reservations` - Create reservation (requires API key, supports idempotency)
- `POST /reservations/{reservation_id}/confirm` - Confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel reservation (requires API key)
- `GET /reservations/{reservation_id}` - Get reservation details

### Orders
- `GET /orders` - List orders with pagination (optional API key for higher limits)
- `GET /orders/{order_id}` - Get order details

## Configuration

Set the API key via environment variable:
```bash
export API_KEY=your-secret-key
```

Default key is `dev-key-change-in-production`.

## Database

The service uses SQLite with automatic initialization. The database file is stored as `commerce.db`.
