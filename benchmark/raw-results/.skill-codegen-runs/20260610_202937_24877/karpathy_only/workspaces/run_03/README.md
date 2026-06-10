# Commerce Inventory & Order API

A FastAPI-based service for managing product inventory, reservations, and orders.

## Setup

Install dependencies:
```bash
pip install -e ".[dev]"
```

## Running the Server

```bash
python -m uvicorn src.commerce_service.app:app --reload
```

The server will start at `http://localhost:8000`.

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock level for a SKU
- `POST /reservations` - Create a reservation (with idempotency)
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - List orders with pagination

All mutating endpoints require an `X-API-Key` header.

## Testing

Run tests with:
```bash
pytest
```

## Database

SQLite database is automatically initialized on startup.
