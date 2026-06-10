# Commerce Service

A FastAPI-based Inventory & Order management system with reservation support and idempotency guarantees.

## Installation

```bash
pip install -e ".[dev]"
```

## Running the Server

```bash
uvicorn src.commerce_service.app:app --reload
```

## API Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header:

```bash
curl -H "X-API-Key: test-key-123" http://localhost:8000/health
```

## Endpoints

### Health Check
- `GET /health` - No auth required

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock levels for a SKU

### Reservations
- `POST /reservations` - Reserve stock with idempotency
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a pending reservation

### Orders
- `GET /orders` - List orders with pagination

## Key Features

- **Idempotent Reservations**: Same `idempotency_key` returns cached response
- **Expiration Handling**: Reservations older than 300 seconds auto-expire on confirm
- **Stock Validation**: Prevents double-reservation with proper stock deduction
- **Pagination**: Orders endpoint supports page/size parameters
- **API Key Security**: All mutations require valid API key

## Testing

```bash
pytest tests/ -v
```
