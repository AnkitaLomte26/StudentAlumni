import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["SESSION_HTTPS_ONLY"] = "false"
os.environ["FRONTEND_ORIGINS"] = "http://testserver"
os.environ["FRONTEND_ORIGIN"] = "http://testserver"
os.environ["ENVIRONMENT"] = "test"
os.environ["ALLOWED_HOSTS"] = "testserver"

from tests.http_client import TestClient
import pytest

from app.database import Base, engine
from app.main import app
from app.models import AlumniProfile, StudentProfile, User  # noqa: F401


@pytest.fixture(autouse=True)
def reset_rate_limits():
    from app.utils.rate_limit import limiter
    limiter.clear()
    yield
    limiter.clear()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "VERIFICATION_STORAGE_DIR", str(tmp_path / "proofs"))
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


STUDENT = {
    "name": "Ada Student",
    "email": "ada.student@example.com",
    "password": "Password123",
    "role": "STUDENT",
    "branch": "Computer Science",
    "graduation_year": 2027,
    "current_year": 3,
    "bio": "Looking for alumni guidance.",
}

ALUMNI = {
    "name": "Alan Alumni",
    "email": "alan.alumni@example.com",
    "password": "Password123",
    "role": "ALUMNI",
    "branch": "Electrical Engineering",
    "graduation_year": 2018,
    "bio": "Happy to help students.",
    "accepting_guidance_requests": True,
}
