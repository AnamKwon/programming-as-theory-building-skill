# Commerce Inventory & Order API

A FastAPI-based service for managing product SKUs, inventory stock levels, reservations, and orders.

## Features

- SKU and inventory management
- Stock reservation with idempotency support
- Reservation confirmation with expiration validation
- Order tracking
- API key-based authentication for mutations
- Paginated order listing

## Setup

### Installation

```bash
pip install -e ".[dev]"
```

### Environment Variables

Create a `.env` file:

```
API_KEY=your-secret-api-key
DATABASE_URL=sqlite:///./commerce.db
```

### Running the Server

```bash
uvicorn src.commerce_service.app:app --reload
```

The server starts on `http://localhost:8000`

## API Endpoints

### Health Check
- `GET /health` - Health check (no authentication required)

### SKU Management
- `POST /skus` - Create a new SKU
- `POST /stock/adjust` - Adjust stock levels

### Reservations
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - List orders with pagination

## Authentication

All mutation endpoints require an `X-API-Key` header with the static API key.

## Testing

```bash
pytest tests/
```
