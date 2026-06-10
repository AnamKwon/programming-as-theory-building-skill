# Commerce Service

A FastAPI-based inventory reservation and order orchestration API.

## Features

- SKU and stock management
- Reservation system with expiration and idempotency
- Order tracking and state transitions
- API key authentication for mutations
- SQLite persistence
- Comprehensive test coverage

## Quick Start

### Install

```bash
pip install -e .
pip install -e ".[dev]"
```

### Run

```bash
python -m uvicorn commerce_service.app:app --reload
```

The service will be available at `http://localhost:8000`. Check `/health` for server status.

### Test

```bash
pytest tests/
```

## API Overview

### Public Endpoints

- `GET /health` — Health check
- `GET /orders/{order_id}` — Retrieve order by ID
- `GET /orders` — List orders with pagination

### Authenticated Endpoints (require `X-API-Key` header)

- `POST /skus` — Create a SKU
- `POST /stock/adjust` — Adjust stock for a SKU
- `POST /reservations` — Create a reservation (idempotent)
- `POST /reservations/{reservation_id}/confirm` — Confirm a reservation
- `POST /reservations/{reservation_id}/cancel` — Cancel a reservation

## Design

**Models:** SQLAlchemy ORM mapping to SKU, Stock, Reservation, and Order tables.

**Repository:** Data access layer isolating database operations.

**Service:** Business logic enforcing stock availability, reservation expiration, idempotency, and order state transitions.

**Security:** API key validation on mutating endpoints via Pydantic dependency.

## Configuration

Set `API_KEY` environment variable for authentication. Default is `dev-key` for testing.
