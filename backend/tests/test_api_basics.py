from app.db import get_db
from app.main import app


async def test_health_ok(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}
    assert len(response.headers["X-Request-ID"]) == 32


async def test_request_id_is_echoed_when_safe_and_replaced_otherwise(client):
    assert (await client.get("/api/health", headers={"X-Request-ID": "abc-123"})).headers["X-Request-ID"] == "abc-123"
    bad = await client.get("/api/health", headers={"X-Request-ID": "x\nforged log line"})
    assert bad.headers["X-Request-ID"] != "x\nforged log line"


async def test_health_reports_db_down(client):
    class BrokenSession:
        async def execute(self, *_):
            raise ConnectionRefusedError

    app.dependency_overrides[get_db] = lambda: BrokenSession()
    response = await client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "db_unavailable"


async def test_unknown_route_uses_error_envelope(client):
    response = await client.get("/api/nope")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == response.headers["X-Request-ID"]


async def test_unhandled_exception_returns_500_envelope(client):
    @app.get("/api/_boom")
    async def boom():
        raise RuntimeError("secret detail")

    try:
        response = await client.get("/api/_boom")
    finally:
        app.router.routes.pop()
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret detail" not in response.text
