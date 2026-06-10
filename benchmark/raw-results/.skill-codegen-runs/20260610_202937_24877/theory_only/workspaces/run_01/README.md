# Commerce Inventory & Order API

A FastAPI-based service for managing product SKUs, inventory, reservations, and orders.

## Features

- SKU management with stock tracking
- Inventory adjustments
- Idempotent reservation system with expiration
- Order confirmation and cancellation workflows
- Paginated order listing
- API token-based authentication

## Installation

```bash
pip install -e ".[dev]"
```

## Running

```bash
uvicorn commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create a new SKU
- `POST /stock/adjust` - Adjust stock for a SKU
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - List orders with pagination

## API Token

All mutating endpoints require an API token via `X-API-Token` header.
