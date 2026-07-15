from starlette.testclient import TestClient

from server import build_server


def test_health_returns_ok():
    mcp = build_server()
    app = mcp.http_app(path="/docs-mcp", host_origin_protection=False)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.text == "ok"
