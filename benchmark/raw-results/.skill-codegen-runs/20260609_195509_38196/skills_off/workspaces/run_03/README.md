# Commerce Service

A production-grade inventory reservation and order orchestration API for small commerce backends.

## Features

- **SKU Management**: Create and manage inventory items with stock tracking
- **Stock Adjustment**: Add or remove inventory with validation
- **Reservations**: Reserve stock with automatic expiration
- **Idempotency**: Safe retries using idempotency keys
- **Order Orchestration**: Manage reservation confirmation and order state
- **API Security**: Key-based authentication for mutating operations
- **Pagination**: Efficient order lookup with cursor-based pagination

## Getting Started

### Installation

```bash
pip install -e ".[dev]"
```

### Running the Service

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Running Tests

```bash
pytest
```

## API Endpoints

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a new SKU (requires API key)
- `POST /skus/{sku_id}/stock` - Adjust stock level (requires API key)

### Reservations
- `POST /reservations` - Create a new reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination

## Configuration

Set `API_KEY` environment variable to enable mutation endpoints:

```bash
export API_KEY=your-secret-key
```

Reservation TTL defaults to 15 minutes and can be configured via `RESERVATION_TTL_MINUTES`.

## Database

SQLite database is stored at `commerce.db` in the working directory.
