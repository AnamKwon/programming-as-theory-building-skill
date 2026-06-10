# Commerce Inventory & Order API

A FastAPI-based service for managing product inventory, reservations, and orders with idempotency and expiration guarantees.

## Quick Start

### Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

### Running the Server

```bash
python -m uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

Health check: `curl http://localhost:8000/health`

### Running Tests

```bash
pytest tests/ -v
```

## API Endpoints

### Health
- `GET /health` - Returns `{"status": "ok"}`

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
  - Requires API Key authentication
  - Body: `{"sku": "STRING", "initial_stock": INT}`

### Stock Operations
- `POST /stock/adjust` - Adjust stock level for a SKU
  - Requires API Key authentication
  - Body: `{"sku": "STRING", "amount": INT}`

### Reservations
- `POST /reservations` - Create a reservation
  - Requires API Key authentication
  - Body: `{"sku": "STRING", "quantity": INT, "idempotency_key": "STRING"}`
  - Returns 201 on success, 400 if insufficient stock or idempotency key exists

- `POST /reservations/{id}/confirm` - Confirm a pending reservation
  - Requires API Key authentication
  - Creates an order record
  - Returns 400 if reservation expired (>300s old) or not in PENDING state

- `POST /reservations/{id}/cancel` - Cancel a reservation
  - Requires API Key authentication
  - Restores stock
  - Returns 400 if not in PENDING state

### Orders
- `GET /orders` - List orders with pagination
  - Query params: `page` (default 1), `size` (default 10)
  - Returns paginated order list

## Architecture

- **models.py** - Pydantic request/response schemas
- **repository.py** - Data access layer (SQLite)
- **service.py** - Business logic layer
- **security.py** - Authentication via API key
- **app.py** - FastAPI application and endpoints

## Environment Variables

- `API_KEY` - Static API key for authentication (default: "test-key")
