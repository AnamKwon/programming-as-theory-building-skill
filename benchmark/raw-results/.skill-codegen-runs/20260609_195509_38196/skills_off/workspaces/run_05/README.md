# Commerce Service

A production-ready inventory reservation and order orchestration API for small commerce backends.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Inventory Reservation**: Reserve stock with automatic expiration
- **Order Orchestration**: Create, confirm, and cancel orders with state transitions
- **Idempotency**: Automatic deduplication of requests via idempotency keys
- **Authentication**: API key validation for mutation endpoints
- **Pagination**: Efficient order listing with cursor-based pagination

## Quick Start

### Install Dependencies

```bash
pip install -e ".[dev]"
```

### Run the Service

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Run Tests

```bash
pytest
```

## API Endpoints

### Health Check
- `GET /health` - Service health status

### SKU Management
- `POST /skus` - Create a new SKU (requires API key)
- `PUT /skus/{sku_id}/stock` - Adjust stock level (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `PUT /reservations/{reservation_id}/confirm` - Confirm a reservation to order (requires API key)
- `PUT /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination (requires API key)

## Architecture

### Layers

- **API Layer** (`app.py`): FastAPI routes, validation, HTTP responses
- **Service Layer** (`service.py`): Business logic, invariant enforcement, state transitions
- **Repository Layer** (`repository.py`): SQLite CRUD operations
- **Models** (`models.py`): Pydantic schemas and SQLAlchemy ORM models
- **Security** (`security.py`): API key validation

### Core Concepts

- **SKU**: Stock keeping unit (product identifier)
- **Reservation**: Temporary hold on inventory with expiration
- **Order**: Confirmed reservation that represents a real transaction
- **Idempotency Key**: Unique token for duplicate request detection
- **Pagination Cursor**: Base64-encoded position marker for efficient listing

## Configuration

Set environment variables:

```bash
DATABASE_URL=sqlite:///./commerce.db
API_KEY=your-secret-api-key
RESERVATION_TTL_MINUTES=15
```

## Design Philosophy

- **Clear Boundaries**: Repository pattern isolates database concerns
- **Service Layer Rules**: Business logic lives in one place
- **Fail-Safe Defaults**: Stock levels are validated before operations
- **Production-Ready**: Pagination, idempotency, proper error handling
- **Testable**: Dependency injection enables isolated testing
