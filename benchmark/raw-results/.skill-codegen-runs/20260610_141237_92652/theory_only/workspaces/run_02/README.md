# Commerce Inventory & Order API

A FastAPI-based service for managing inventory and orders with reservation support, idempotency, and expiration handling.

## Architecture

- **app.py**: FastAPI routes and HTTP layer
- **service.py**: Business logic and orchestration
- **repository.py**: Data access layer (SQLite)
- **models.py**: Pydantic request/response schemas
- **security.py**: API key authentication

## API Endpoints

### Health Check
- `GET /health` - Health status check (no auth required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock (requires API key)
- `POST /stock/adjust` - Adjust stock levels (requires API key)

### Reservations
- `POST /reservations` - Create a reservation with idempotency (requires API key)
- `POST /reservations/{id}/confirm` - Confirm a pending reservation (requires API key)
- `POST /reservations/{id}/cancel` - Cancel a pending reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination

## Key Features

- **Idempotent Reservations**: Same idempotency_key returns cached result without double-deduction
- **Expiration Handling**: Reservations expire after 300 seconds
- **Stock Management**: Automatic stock adjustment on reservation/cancellation
- **API Key Authentication**: Static token validation for mutating endpoints

## Running

```bash
pip install -e ".[dev]"
uvicorn src.commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/ -v
```
