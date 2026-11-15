import pytest
from httpx import AsyncClient
from backend.main import app
from backend.models.enums import OrderStatus
from fastapi.testclient import TestClient

@pytest.fixture(scope="function")
def client():
    with TestClient(app) as c:
        yield c

def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "ShopFlow API is running"}

def test_create_order(client):
    order_data = {
        "user_id": "usr_123",
        "total_amount": 99.99,
        "items": [],
        "status": "pending"
    }
    response = client.post("/orders", json=order_data)
    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == "usr_123"
    assert data["total_amount"] == 99.99
    assert data["items"] == []
    assert data["status"] == "pending"
    assert "id" in data
    assert "created_at" in data

def test_list_orders(client):
    # Create one order first
    client.post("/orders", json={
        "user_id": "usr_456",
        "total_amount": 42.0,
        "items": [],
        "status": "pending"
    })
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["user_id"] == "usr_456"

def test_get_order(client):
    # Create order
    create_resp = client.post("/orders", json={
        "user_id": "usr_789",
        "total_amount": 123.45,
        "items": [],
        "status": "pending"
    })
    order_id = create_resp.json()["id"]

    # Get it
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["user_id"] == "usr_789"
    assert data["total_amount"] == 123.45
    assert data["items"] == []

def test_update_order_status_valid(client):
    # Create order
    create_resp = client.post("/orders", json={
        "user_id": "usr_abc",
        "total_amount": 50.0,
        "items": [],
        "status": "pending"
    })
    order_id = create_resp.json()["id"]

    # Update to confirmed
    response = client.put(f"/orders/{order_id}/status", json={"new_status": "confirmed"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmed"

def test_update_order_status_invalid_transition(client):
    # Create order
    create_resp = client.post("/orders", json={
        "user_id": "usr_def",
        "total_amount": 50.0,
        "items": [],
        "status": "delivered"
    })
    order_id = create_resp.json()["id"]

    # Try to go back to pending
    response = client.put(f"/orders/{order_id}/status", json={"new_status": "pending"})
    assert response.status_code == 422

def test_update_order_status_invalid_value(client):
    # Create order
    create_resp = client.post("/orders", json={
        "user_id": "usr_ghi",
        "total_amount": 50.0,
        "items": [],
        "status": "pending"
    })
    order_id = create_resp.json()["id"]

    # Invalid status
    response = client.put(f"/orders/{order_id}/status", json={"new_status": "invalid_status"})
    assert response.status_code == 422

def test_delete_order(client):
    # Create order
    create_resp = client.post("/orders", json={
        "user_id": "usr_jkl",
        "total_amount": 50.0,
        "items": [],
        "status": "pending"
    })
    order_id = create_resp.json()["id"]

    # Delete it
    response = client.delete(f"/orders/{order_id}")
    assert response.status_code == 204

    # Verify it's gone
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 404

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ready"}