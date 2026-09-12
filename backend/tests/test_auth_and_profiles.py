from app.database import SessionLocal
from app.models import User, VerificationStatus
from tests.conftest import ALUMNI, STUDENT


def test_student_registration_succeeds(client):
    response = client.post("/api/auth/register", json=STUDENT)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == STUDENT["email"]
    assert body["role"] == "STUDENT"
    assert body["account_status"] == "ACTIVE"
    assert "password_hash" not in body
    assert "password" not in body


def test_alumni_registration_succeeds(client):
    response = client.post("/api/auth/register", json=ALUMNI)
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "ALUMNI"
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == ALUMNI["email"]).one()
        assert user.alumni_profile is not None
        assert user.alumni_profile.verification_status == VerificationStatus.PENDING
        assert user.student_profile is None
    finally:
        db.close()


def test_duplicate_email_is_rejected(client):
    client.post("/api/auth/register", json=STUDENT)
    response = client.post("/api/auth/register", json=STUDENT)
    assert response.status_code == 409
    assert "already registered" in response.json()["detail"].lower()


def test_stored_password_is_hashed(client):
    client.post("/api/auth/register", json=STUDENT)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == STUDENT["email"]).one()
        assert user.password_hash != STUDENT["password"]
        assert user.password_hash.startswith("$argon2")
    finally:
        db.close()


def test_valid_login_succeeds(client):
    client.post("/api/auth/register", json=STUDENT)
    response = client.post(
        "/api/auth/login",
        json={"email": STUDENT["email"], "password": STUDENT["password"]},
    )
    assert response.status_code == 200
    assert response.json()["email"] == STUDENT["email"]
    assert "session" in response.cookies


def test_wrong_password_fails(client):
    client.post("/api/auth/register", json=STUDENT)
    response = client.post(
        "/api/auth/login",
        json={"email": STUDENT["email"], "password": "WrongPass1"},
    )
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


def test_me_without_login_returns_401(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_after_login_returns_user(client):
    client.post("/api/auth/register", json=STUDENT)
    client.post(
        "/api/auth/login",
        json={"email": STUDENT["email"], "password": STUDENT["password"]},
    )
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == STUDENT["name"]
    assert body["email"] == STUDENT["email"]
    assert body["role"] == "STUDENT"
    assert "password_hash" not in body


def test_logout_removes_authentication(client):
    client.post("/api/auth/register", json=STUDENT)
    client.post(
        "/api/auth/login",
        json={"email": STUDENT["email"], "password": STUDENT["password"]},
    )
    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_student_cannot_access_alumni_profile(client):
    client.post("/api/auth/register", json=STUDENT)
    client.post(
        "/api/auth/login",
        json={"email": STUDENT["email"], "password": STUDENT["password"]},
    )
    response = client.get("/api/profiles/alumni/me")
    assert response.status_code == 403
    update = client.put("/api/profiles/alumni/me", json={"bio": "nope"})
    assert update.status_code == 403


def test_alumni_cannot_access_student_profile(client):
    client.post("/api/auth/register", json=ALUMNI)
    client.post(
        "/api/auth/login",
        json={"email": ALUMNI["email"], "password": ALUMNI["password"]},
    )
    response = client.get("/api/profiles/student/me")
    assert response.status_code == 403
    update = client.put("/api/profiles/student/me", json={"bio": "nope"})
    assert update.status_code == 403


def test_student_profile_update_works(client):
    client.post("/api/auth/register", json=STUDENT)
    client.post(
        "/api/auth/login",
        json={"email": STUDENT["email"], "password": STUDENT["password"]},
    )
    response = client.put(
        "/api/profiles/student/me",
        json={"branch": "Information Technology", "current_year": 4, "bio": "Updated bio."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["branch"] == "Information Technology"
    assert body["current_year"] == 4
    assert body["bio"] == "Updated bio."
    assert body["graduation_year"] == STUDENT["graduation_year"]
