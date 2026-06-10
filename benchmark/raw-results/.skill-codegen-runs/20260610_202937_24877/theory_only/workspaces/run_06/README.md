# Commerce Inventory & Order API

A FastAPI-based service for managing product inventory, reservations, and orders.

## Features

- SKU and inventory management
- Reservation system with idempotency
- Order creation and tracking
- Pagination support
- API token authentication on mutating endpoints

## Setup

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running

```bash
uvicorn src.commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/ -v
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create a new SKU
- `POST /stock/adjust` - Adjust stock levels
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - Get paginated orders

## Authentication

All mutating endpoints require an `X-API-Key` header with a valid API token.
