import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.database import Base, engine, get_db
from backend.models.inventory import Inventory

# Override dependency for testing to use a separate session per test or transaction rollback
# This is a more robust pattern than dropping/creating tables every time

@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    connection = engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = TestingSessionLocal()
    
    # Drop all and recreate to ensure clean state for integration-like tests
    # Alternatively, use nested transactions for speed, but create_all is safer for schema changes
    Base.metadata.drop_all(bind=connection)
    Base.metadata.create_all(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db_session):
    """Create a test client with overridden DB dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass # Session is closed by fixture teardown

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

class TestInventoryAPI:
    def test_create_inventory_success(self, client):
        """Test successful creation of an inventory item."""
        payload = {
            "product_name": "Test Product",
            "sku": "TEST-SKU-001",
            "quantity": 100,
            "unit_price": 9.99
        }
        response = client.post("/inventory/", json=payload)
        
        assert response.status_code == 201 # Changed to 201 Created
        data = response.json()
        assert data["product_name"] == "Test Product"
        assert data["sku"] == "TEST-SKU-001"
        assert data["quantity"] == 100
        assert data["unit_price"] == 9.99

    def test_create_inventory_duplicate_error(self, client):
        """Test that creating a duplicate product name returns 400."""
        payload = {
            "product_name": "Duplicate Product",
            "sku": "DUP-SKU-001",
            "quantity": 50,
            "unit_price": 5.50
        }
        resp1 = client.post("/inventory/", json=payload)
        assert resp1.status_code == 201
        
        resp2 = client.post("/inventory/", json=payload)
        assert resp2.status_code == 400
        assert "already exists" in resp2.json()["detail"].lower()

    def test_get_inventory_list(self, client):
        """Test retrieving the list of all inventory items."""
        client.post("/inventory/", json={
            "product_name": "Item A",
            "sku": "SKU-A",
            "quantity": 10,
            "unit_price": 1.0
        })
        client.post("/inventory/", json={
            "product_name": "Item B",
            "sku": "SKU-B",
            "quantity": 20,
            "unit_price": 2.0
        })
        
        response = client.get("/inventory/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        names = [item["product_name"] for item in data]
        assert "Item A" in names
        assert "Item B" in names

    def test_get_single_inventory_success(self, client):
        """Test retrieving a specific inventory item by product name."""
        payload = {
            "product_name": "Specific Item",
            "sku": "SPEC-001",
            "quantity": 5,
            "unit_price": 100.0
        }
        client.post("/inventory/", json=payload)
        
        response = client.get("/inventory/Specific Item")
        assert response.status_code == 200
        data = response.json()
        assert data["product_name"] == "Specific Item"
        assert data["quantity"] == 5

    def test_get_single_inventory_not_found(self, client):
        """Test retrieving a non-existent inventory item returns 404."""
        response = client.get("/inventory/NonExistent")
        assert response.status_code == 404
        
    def test_update_inventory_quantity(self, client):
        """Test updating inventory quantity via PATCH."""
        payload = {
            "product_name": "Update Me",
            "sku": "UPD-001",
            "quantity": 10,
            "unit_price": 5.0
        }
        client.post("/inventory/", json=payload)
        
        update_payload = {"quantity": 8}
        response = client.patch("/inventory/Update Me", json=update_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["quantity"] == 8
        
    def test_update_inventory_price(self, client):
        """Test updating inventory unit price via PATCH."""
        payload = {
            "product_name": "Price Change",
            "sku": "PRC-001",
            "quantity": 10,
            "unit_price": 5.0
        }
        client.post("/inventory/", json=payload)
        
        update_payload = {"unit_price": 7.5}
        response = client.patch("/inventory/Price Change", json=update_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["unit_price"] == 7.5


class TestOrderInventoryIntegration:
    def test_order_deducts_stock_success(self, client):
        """Test that placing an order correctly deducts stock."""
        inv_payload = {
            "product_name": "Stocked Item",
            "sku": "STK-001",
            "quantity": 10,
            "unit_price": 2.0
        }
        client.post("/inventory/", json=inv_payload)
        
        order_payload = {
            "customer_name": "Alice",
            "items": [
                {"product_name": "Stocked Item", "quantity": 3}
            ]
        }
        response = client.post("/orders/", json=order_payload)
        assert response.status_code == 201 # Changed to 201
        
        get_resp = client.get("/inventory/Stocked Item")
        assert get_resp.status_code == 200
        assert get_resp.json()["quantity"] == 7

    def test_order_insufficient_stock(self, client):
        """Test that ordering more than available stock fails."""
        inv_payload = {
            "product_name": "Low Stock",
            "sku": "LOW-001",
            "quantity": 2,
            "unit_price": 5.0
        }
        client.post("/inventory/", json=inv_payload)
        
        order_payload = {
            "customer_name": "Bob",
            "items": [
                {"product_name": "Low Stock", "quantity": 5}
            ]
        }
        response = client.post("/orders/", json=order_payload)
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_order_product_not_in_inventory(self, client):
        """Test that ordering a product not in inventory fails."""
        order_payload = {
            "customer_name": "Charlie",
            "items": [
                {"product_name": "Ghost Product", "quantity": 1}
            ]
        }
        response = client.post("/orders/", json=order_payload)
        assert response.status_code == 400
        assert "does not exist in inventory" in response.json()["detail"]

    def test_order_empty_items_no_check(self, client):
        """Test that empty items list creates order without inventory check."""
        order_payload = {
            "customer_name": "Dave",
            "items": []
        }
        response = client.post("/orders/", json=order_payload)
        assert response.status_code == 201
        data = response.json()
        assert data["total_amount"] == 0.0
        assert data["customer_name"] == "Dave"