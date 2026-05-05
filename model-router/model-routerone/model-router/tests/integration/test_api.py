from fastapi.testclient import TestClient
from model_router_api import app

client = TestClient(app)

def test_api_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_model_generation():
    response = client.post(
        "/generate",
        json={"model": "qwen-turbo", "input": "你好"}
    )
    assert response.status_code == 200
    assert "output" in response.json()

def test_invalid_model():
    response = client.post(
        "/generate",
        json={"model": "invalid-model", "input": "你好"}
    )
    assert response.status_code == 400
    assert "error" in response.json()

def test_cache_functionality():
    # Assuming there's an endpoint to test cache
    response = client.post(
        "/generate",
        json={"model": "qwen-turbo", "input": "你好"}
    )
    assert response.status_code == 200
    first_output = response.json()["output"]

    # Call again to check if cache is used
    response = client.post(
        "/generate",
        json={"model": "qwen-turbo", "input": "你好"}
    )
    assert response.status_code == 200
    second_output = response.json()["output"]

    # Check if the outputs are the same, indicating cache was used
    assert first_output == second_output

def test_model_scorer():
    response = client.get("/models/score")
    assert response.status_code == 200
    assert "best_model" in response.json()