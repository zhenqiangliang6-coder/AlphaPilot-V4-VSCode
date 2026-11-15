# ShopFlow Order API Specification

## Overview

This document describes the RESTful API for managing e-commerce orders in the ShopFlow system.

All endpoints are prefixed with `/orders`.

---

## Endpoints

### POST `/`

Create a new order.

**Request Body (JSON)**:
{
  "user_id": "string",
  "total_amount": 0.0,
  "items": [],
  "status": "pending"
}

**Response (200 OK)**:
{
  "id": 1,
  "user_id": "string",
  "status": "pending",
  "total_amount": 0.0,
  "items": [],
  "created_at": "2023-01-01T00:00:00"
}

---

### GET `/`

Retrieve all orders.

**Response (200 OK)**:
[
  {
    "id": 1,
    "user_id": "string",
    "status": "pending",
    "total_amount": 0.0,
    "items": [],
    "created_at": "2023-01-01T00:00:00"
  }
]

---

### GET `/{order_id}`

Retrieve a specific order by ID.

**Response (200 OK)**:
{
  "id": 1,
  "user_id": "string",
  "status": "pending",
  "total_amount": 0.0,
  "items": [],
  "created_at": "2023-01-01T00:00:00"
}

**Error (404 Not Found)**:
{"detail": "Order not found"}

---

### PUT `/{order_id}/status`

Update the status of an order.

**Request Body (JSON)**:
{"new_status": "confirmed"}

**Valid Transitions**:
- `pending` → `confirmed`, `cancelled`
- `confirmed` → `shipped`, `cancelled`
- `shipped` → `delivered`, `cancelled`
- `delivered` → `cancelled`
- `cancelled` → (no transitions)

**Response (200 OK)**:
{
  "id": 1,
  "user_id": "string",
  "status": "confirmed",
  "total_amount": 0.0,
  "items": [],
  "created_at": "2023-01-01T00:00:00"
}

**Error (422 Unprocessable Entity)**:
- Invalid `new_status` value
- Disallowed state transition

---

### DELETE `/{order_id}`

Delete an order.

**Response (204 No Content)** — no body.

**Error (404 Not Found)**:
{"detail": "Order not found"}

---

## Status Model

| Enum Member | Value      | Description                     |
|-------------|------------|-------------------------------------|
| `PENDING`   | `"pending"`  | Initial state after creation       |
| `CONFIRMED` | `"confirmed"`| Payment verified                   |
| `SHIPPED`   | `"shipped"`  | Package dispatched                 |
| `DELIVERED` | `"delivered"`| Customer received                  |
| `CANCELLED` | `"cancelled"`| Final state; no further transitions|

---

## Notes

- All `items` are stored as a JSON array in the `items` column; no separate `order_items` table.
- `created_at` is timezone-naive UTC.
- Database uses SQLite with file path `./backend/shopflow.db`.
- All datetime fields are serialized as ISO 8601 strings.