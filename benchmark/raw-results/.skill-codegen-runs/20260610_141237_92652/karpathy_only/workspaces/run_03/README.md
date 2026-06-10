# Commerce Service API

A FastAPI-based inventory and order management service with reservation support.

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running

```bash
python -m uvicorn src.commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create a new SKU
- `POST /stock/adjust` - Adjust stock levels
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - List orders (paginated)

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header.
