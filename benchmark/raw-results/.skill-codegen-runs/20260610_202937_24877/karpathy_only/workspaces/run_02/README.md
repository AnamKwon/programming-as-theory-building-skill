# Commerce Inventory & Order API

A FastAPI-based microservice for managing inventory SKUs, reservations, and orders.

## Features

- **SKU Management**: Create and manage product SKUs with stock tracking
- **Stock Adjustment**: Adjust stock levels with real-time updates
- **Reservations**: Reserve inventory with idempotency and expiration checks
- **Orders**: Confirm reservations and track orders with pagination
- **Authentication**: API token-based security on all mutating endpoints
- **Validation**: Comprehensive stock, state, and expiration checks

## Installation

```bash
pip install -e ".[dev]"
```

## Running

```bash
python -m uvicorn src.commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/ -v
```

## API Endpoints

- `GET /health` - Health check (no auth)
- `POST /skus` - Create SKU (requires API key)
- `POST /stock/adjust` - Adjust stock (requires API key)
- `POST /reservations` - Create reservation (requires API key)
- `POST /reservations/{id}/confirm` - Confirm reservation (requires API key)
- `POST /reservations/{id}/cancel` - Cancel reservation (requires API key)
- `GET /orders` - List orders with pagination (requires API key)

## Authentication

All mutating endpoints require an `X-API-Key` header with a valid API token.
Default test token: `test-api-key-12345`
