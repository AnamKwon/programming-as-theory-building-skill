# Commerce Inventory & Order API

A FastAPI-based service for managing product inventory, stock reservations, and orders.

## Features

- SKU management with stock tracking
- Inventory adjustments
- Idempotent reservation system with expiration handling
- Order creation and pagination
- API token-based security for all mutations

## API Endpoints

### Health Check
- `GET /health` - Service health status

### Inventory Management
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock for a SKU

### Reservations
- `POST /reservations` - Create a reservation (with idempotency)
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation and restore stock

### Orders
- `GET /orders` - Retrieve paginated orders

## Running

```bash
pip install -e ".[dev]"
uvicorn src.commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/ -v
```

## Configuration

Set `API_TOKEN` environment variable to control the API token (default: "test-token").
