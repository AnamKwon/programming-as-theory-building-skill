# Commerce Service

A FastAPI-based inventory reservation and order orchestration service.

## Features

- SKU and stock management
- Reservation system with expiration and idempotency
- Order state machine (reserved → confirmed → cancelled)
- API key authentication for mutations
- SQLite persistence
- Comprehensive error handling

## Setup

```bash
pip install -e ".[dev]"
```

## Run

```bash
python -m uvicorn commerce_service.app:app --reload
```

Health check: `GET /health`

## API Endpoints

### Public
- `GET /health` — Health check
- `GET /orders?page=1&page_size=10` — List orders

### Protected (require `X-API-Key` header)
- `POST /skus` — Create a SKU
- `POST /stock` — Adjust stock
- `POST /reservations` — Create a reservation
- `POST /reservations/{id}/confirm` — Confirm reservation
- `POST /reservations/{id}/cancel` — Cancel reservation

## Tests

```bash
pytest
```
