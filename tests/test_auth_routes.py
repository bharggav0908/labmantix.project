from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_login_page_loads():
    response = client.get("/login")
    assert response.status_code == 200
    assert "Welcome back" in response.text
