# Commerce Inventory & Order API

A FastAPI-based service for managing inventory SKUs, stock reservations, and orders.

## Setup

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running the Server

```bash
python -m commerce_service
```

The server will start on `http://localhost:8000`.

## API Endpoints

### Health Check
- `GET /health` - Returns service status

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock level for a SKU

### Reservations
- `POST /reservations` - Reserve stock with idempotency
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - Get paginated orders

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Token` header with a valid token.

## Running Tests

```bash
pytest tests/
```
