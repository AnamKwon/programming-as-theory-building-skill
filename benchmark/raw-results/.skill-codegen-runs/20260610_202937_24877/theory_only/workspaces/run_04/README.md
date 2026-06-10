# Commerce Inventory & Order API

A FastAPI-based service for managing inventory SKUs, stock reservations, and orders with idempotent operations and expiration handling.

## Setup

Install dependencies:
```bash
pip install -e ".[dev]"
```

## Running

Start the server:
```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at http://localhost:8000/docs

## Testing

Run tests:
```bash
pytest
```

## API Authentication

All mutating endpoints require an `X-API-Key` header with the correct API token.

## Core Endpoints

- `GET /health` - Health check (no auth)
- `POST /skus` - Create a new SKU
- `POST /stock/adjust` - Adjust stock levels
- `POST /reservations` - Create a reservation (idempotent)
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - List orders (paginated)
