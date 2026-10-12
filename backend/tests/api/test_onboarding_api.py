from fastapi.testclient import TestClient


def test_endpoints_require_login(client: TestClient) -> None:
    assert client.get("/api/onboarding").status_code == 401
    assert client.post("/api/onboarding/numbering-checked").status_code == 401
    assert client.post("/api/onboarding/dismiss").status_code == 401


def test_checklist(user_client: TestClient) -> None:
    body = user_client.get("/api/onboarding").json()
    assert body == {
        "steps": [
            {"key": "company", "done": False},
            {"key": "bank_account", "done": False},
            {"key": "numbering", "done": False},
            {"key": "customers", "done": False},
            {"key": "first_invoice", "done": False},
            {"key": "backup", "done": False},
        ],
        "dismissed": False,
        "complete": False,
    }
    checked = user_client.post("/api/onboarding/numbering-checked").json()
    assert {"key": "numbering", "done": True} in checked["steps"]
    assert user_client.post("/api/onboarding/dismiss").json()["dismissed"]
    assert not user_client.post("/api/onboarding/show").json()["dismissed"]
