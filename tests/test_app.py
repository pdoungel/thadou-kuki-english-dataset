from fastapi.testclient import TestClient

from app.backend.main import app, init_db

init_db()
client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_directions():
    response = client.get("/api/translation-directions")
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert ids == {"thadou_to_english", "english_to_thadou"}
