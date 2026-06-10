# Commerce Inventory & Order API

A FastAPI-based service for managing inventory SKUs, reservations, and orders with idempotent operations and stock management.

## Features

- SKU management with stock tracking
- Reservation system with idempotency support
- Order creation from confirmed reservations
- Automatic stock restoration on cancellation
- Reservation expiration enforcement (300 seconds)
- API key-based authentication for mutations
- Paginated order retrieval

## Installation

```bash
pip install -e .
```

## Development

```bash
pip install -e ".[dev]"
```

## Running the Service

```bash
uvicorn src.commerce_service.app:app --reload
```

## API Documentation

Once running, visit:
- http://localhost:8000/docs (Swagger UI)
- http://localhost:8000/redoc (ReDoc)

## Testing

```bash
pytest tests/
```

## Environment Variables

- `API_KEY`: Required API key for mutation endpoints (default: "test-key-12345")
- `DATABASE_URL`: SQLite database path (default: "sqlite:///./commerce.db")
