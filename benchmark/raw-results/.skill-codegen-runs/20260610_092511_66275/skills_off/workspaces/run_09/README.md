# Commerce Service

A production-ready inventory reservation and order orchestration API.

## Features

- SKU and stock management
- Inventory reservations with automatic expiration
- Order confirmation workflow
- Idempotent reservation creation
- API key-based security
- Pagination for order lookup
- Comprehensive test coverage

## Quick Start

Install dependencies:
```bash
pip install -e .
```

Run the API:
```bash
uvicorn commerce_service.app:app --reload
```

Run tests:
```bash
pytest tests/ -v
```

## API Endpoints

### Public
- `GET /health` - Health check

### Protected (require `X-API-Key` header)
- `POST /skus` - Create a new SKU
- `POST /stock/adjust` - Adjust SKU stock
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - List orders (paginated)
- `GET /orders/{id}` - Get order details

## Configuration

Set the API key via environment variable:
```bash
export COMMERCE_API_KEY="your-secret-key"
```

The database file will be created as `commerce.db` in the current directory.

## Architecture

- **models.py** - Pydantic request/response schemas
- **repository.py** - Database access layer (SQLAlchemy)
- **service.py** - Business logic (stock validation, reservation lifecycle)
- **security.py** - API key authentication
- **app.py** - FastAPI routes and dependencies
