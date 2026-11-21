import pytest
from fastapi.testclient import TestClient

def test_create_order(client: TestClient):
    """Test creating a new order."""
    payload = {
        "user_id": "user_123",
        "items": [],  # Empty list as per requirement
        "total_amount": 99.99
    }
    response = client.post("/orders/", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "user_123"
    assert data["status"] == "pending"
    assert data["total_amount"] == 99.99
    assert "id" in data

def test_list_orders(client: TestClient):
    """Test listing orders."""
    # First create an order
    payload = {
        "user_id": "user_list_test",
        "items": [],
        "total_amount": 50.0
    }
    client.post("/orders/", json=payload)
    
    response = client.get("/orders/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert any(o["user_id"] == "user_list_test" for o in data)

def test_get_single_order(client: TestClient):
    """Test retrieving a single order by ID."""
    payload = {
        "user_id": "user_get_test",
        "items": [],
        "total_amount": 25.0
    }
    create_resp = client.post("/orders/", json=payload)
    order_id = create_resp.json()["id"]
    
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["user_id"] == "user_get_test"

def test_update_status_valid(client: TestClient):
    """Test updating order status with a valid transition."""
    payload = {
        "user_id": "user_update_test",
        "items": [],
        "total_amount": 100.0
    }
    create_resp = client.post("/orders/", json=payload)
    order_id = create_resp.json()["id"]
    
    # pending -> confirmed
    update_payload = {"new_status": "confirmed"}
    response = client.put(f"/orders/{order_id}/status", json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmed"

def test_update_status_invalid_transition(client: TestClient):
    """Test updating order status with an invalid transition (should be 422)."""
    payload = {
        "user_id": "user_invalid_test",
        "items": [],
        "total_amount": 100.0
    }
    create_resp = client.post("/orders/", json=payload)
    order_id = create_resp.json()["id"]
    
    # Try to go from pending directly to delivered (invalid)
    update_payload = {"new_status": "delivered"}
    response = client.put(f"/orders/{order_id}/status", json=update_payload)
    assert response.status_code == 422

def test_delete_order(client: TestClient):
    """Test deleting an order."""
    payload = {
        "user_id": "user_delete_test",
        "items": [],
        "total_amount": 10.0
    }
    create_resp = client.post("/orders/", json=payload)
    order_id = create_resp.json()["id"]
    
    response = client.delete(f"/orders/{order_id}")
    assert response.status_code == 204
    
    # Verify it's gone
    get_response = client.get(f"/orders/{order_id}")
    assert get_response.status_code == 404

def test_get_nonexistent_order(client: TestClient):
    """Test getting an order that doesn't exist."""
    response = client.get("/orders/99999")
    assert response.status_code == 404