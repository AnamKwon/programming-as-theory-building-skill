# Commerce Service

Inventory reservation and order orchestration API for e-commerce backends.

## Setup

Install dependencies:
```bash
pip install -e .
pip install -e ".[dev]"
```

## Running the Service

Start the API server:
```bash
python -m uvicorn src.commerce_service.app:app --reload
```

Server runs on `http://localhost:8000` with docs at `/docs`.

## API Key

Mutating endpoints require an `X-API-Key` header. Default key for development: `test-key-123`.

## Database

SQLite database is auto-initialized on first request and stored in `commerce.db`.

## Testing

Run tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=src.commerce_service tests/
```

## Features

- SKU and stock management
- Inventory reservations with expiration
- Order state transitions
- Idempotent reservation creation
- Pagination for order queries
- API-key authentication for mutations
