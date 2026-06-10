# Commerce Service

A production-ready inventory reservation and order orchestration API built with FastAPI and SQLite.

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Running the Server

```bash
uvicorn commerce_service.app:app --reload
```

Server runs at `http://localhost:8000`

### Running Tests

```bash
pytest tests/ -v
```

## API Endpoints

### Health Check
- `GET /health` — Service health status

### SKU Management
- `POST /skus` — Create a SKU (requires API key)
- `POST /skus/{sku}/adjust-stock` — Adjust stock level (requires API key)

### Reservations
- `POST /reservations` — Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` — Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` — Cancel a reservation (requires API key)

### Orders
- `GET /orders` — List orders with pagination (optional API key for additional features)

## Key Features

- **Stock Management**: Track inventory by SKU
- **Reservation System**: Temporary holds with automatic expiration
- **Order Orchestration**: State machine for order lifecycle
- **Idempotency**: Prevent duplicate orders via idempotency keys
- **API Security**: Key-based authentication for mutations
- **Repository Pattern**: Clean database abstraction
- **Comprehensive Tests**: Happy paths, edge cases, and error scenarios

## Architecture

- `models.py` — Domain and Pydantic models
- `repository.py` — SQLite data access layer
- `service.py` — Business logic and state machines
- `security.py` — API key validation
- `app.py` — FastAPI application and routing
