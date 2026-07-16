import re
import uuid

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_login_page_loads():
    response = client.get("/login")
    assert response.status_code == 200
    assert "Welcome back" in response.text


def test_authenticated_user_can_create_project_and_review():
    test_client = TestClient(app)
    email = f"workflow-{uuid.uuid4().hex}@example.com"
    password = "StrongPass123"

    test_client.post(
        "/signup",
        data={"name": "Workflow Tester", "email": email, "password": password},
        follow_redirects=False,
    )
    dashboard = test_client.get("/dashboard")
    assert dashboard.status_code == 200

    project_response = test_client.post(
        "/projects",
        data={"project_name": "HR Demo Project", "github_url": "https://github.com/example/hr-demo"},
        follow_redirects=False,
    )
    assert project_response.status_code == 303

    dashboard = test_client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "HR Demo Project" in dashboard.text
    assert "No projects yet" not in dashboard.text
    match = re.search(r'<option value="(\d+)">HR Demo Project</option>', dashboard.text)
    assert match is not None

    review_response = test_client.post(
        "/review",
        data={
            "project_id": match.group(1),
            "title": "Demo Review",
            "language": "Python",
            "code": "def add(a, b):\n    return a + b\n",
        },
        follow_redirects=False,
    )
    assert review_response.status_code == 303
    assert review_response.headers["location"].startswith("/review/")
