"""HTTP test client that follows the same CSRF handshake as the frontend."""
from fastapi.testclient import TestClient as BaseClient

class TestClient(BaseClient):
    def request(self, method, url, **kwargs):
        if method.upper() in ("POST","PUT","PATCH","DELETE"):
            headers = dict(kwargs.pop("headers", None) or {})
            token = super().request("GET", "/api/auth/csrf").json()["csrf_token"]
            headers.setdefault("X-CSRF-Token", token)
            kwargs["headers"] = headers
        return super().request(method, url, **kwargs)

