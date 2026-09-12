from datetime import timedelta
import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.database import SessionLocal
from app.models import User, StudentProfile, AlumniProfile
from app.models.professional import GuidanceArea
from app.models.networking import GuidanceRequest, Connection, Notification
from app.services import networking as service
from app.utils.security import hash_password


@pytest.fixture()
def network(client):
    with SessionLocal() as db:
        hashed = hash_password("TestPassword123!")
        for uid in range(1, 11):
            role = "STUDENT" if uid <= 2 else "ALUMNI"
            db.add(User(id=uid, name=f"Person {uid}", email=f"person{uid}@example.com",
                        password_hash=hashed, role=role, account_status="ACTIVE"))
            db.flush()
            if role == "STUDENT":
                db.add(StudentProfile(user_id=uid, branch="ENTC", graduation_year=2027))
            else:
                db.add(AlumniProfile(user_id=uid, branch="ENTC", graduation_year=2020,
                                    verification_status="VERIFIED", accepting_guidance_requests=True))
        db.add(GuidanceArea(id=1, name="Career Guidance"))
        db.commit()
    return client


def login(c, uid=1):
    assert c.post("/api/auth/login", json={"email":f"person{uid}@example.com", "password":"TestPassword123!"}).status_code == 200


def send(c, target=3, **changes):
    return c.post("/api/guidance-requests", json={"alumni_user_id":target, "guidance_area_id":1,
                                               "message":"Please help me prepare for interviews.", **changes})


def pending(c):
    login(c)
    response = send(c)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def accepted(c):
    rid = pending(c)
    login(c, 3)
    assert c.patch(f"/api/guidance-requests/{rid}/accept").status_code == 200
    return rid, c.get("/api/connections").json()["items"][0]["id"]


def test_valid_request_and_notification(network):
    rid = pending(network)
    data = network.get("/api/guidance-requests/my").json()
    assert data["pending_count"] == 1
    assert data["items"][0]["status"] == "PENDING"
    assert "email" not in str(data)
    login(network, 3)
    note = network.get("/api/notifications").json()
    assert note["items"][0]["type"] == "REQUEST_RECEIVED"
    assert note["items"][0]["request_id"] == rid


def test_alumni_cannot_send(network):
    login(network, 3)
    assert send(network).status_code == 403


@pytest.mark.parametrize("field,value", [("verification_status","PENDING"),("verification_status","REJECTED"),("accepting_guidance_requests",False)])
def test_ineligible_alumni(network, field, value):
    with SessionLocal() as db:
        setattr(db.get(AlumniProfile, 3), field, value)
        db.commit()
    login(network)
    assert send(network).status_code == 409


@pytest.mark.parametrize("uid", [1, 3])
def test_inactive_account(network, uid):
    login(network)
    with SessionLocal() as db:
        db.get(User, uid).account_status = "DEACTIVATED"
        db.commit()
    assert send(network).status_code in (401,403,409)


def test_duplicate_pending(network):
    pending(network)
    assert send(network).status_code == 409


def test_database_duplicate_guard(network):
    pending(network)
    with SessionLocal() as db:
        db.add(GuidanceRequest(student_user_id=1, alumni_user_id=3, guidance_area_id=1, message="Duplicate", status="PENDING"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


@pytest.mark.parametrize("action", ["cancel","accept","reject"])
def test_five_pending_limit_and_released_slot(network, action):
    login(network)
    ids = [send(network, uid).json()["id"] for uid in range(3,8)]
    assert send(network, 8).status_code == 409
    if action != "cancel":
        login(network, 3)
    assert network.patch(f"/api/guidance-requests/{ids[0]}/{action}").status_code == 200
    login(network)
    assert send(network, 8).status_code == 201


def test_cancel_own_only(network):
    rid = pending(network)
    login(network, 2)
    assert network.patch(f"/api/guidance-requests/{rid}/cancel").status_code == 404
    login(network)
    result = network.patch(f"/api/guidance-requests/{rid}/cancel")
    assert result.json()["status"] == "CANCELLED"
    assert network.patch(f"/api/guidance-requests/{rid}/cancel").status_code == 409
    assert send(network).status_code == 201


def test_accept_owner_and_connection_both_sides(network):
    rid = pending(network)
    login(network, 4)
    assert network.patch(f"/api/guidance-requests/{rid}/accept").status_code == 404
    login(network, 3)
    assert network.patch(f"/api/guidance-requests/{rid}/accept").json()["status"] == "ACCEPTED"
    first = network.get("/api/connections").json()["items"][0]
    login(network)
    assert network.get("/api/connections").json()["items"][0]["id"] == first["id"]
    assert first["source_request_id"] == rid
    assert send(network).status_code == 409


def test_accept_rollback_after_connection_flush(network, monkeypatch):
    rid = pending(network)
    login(network, 3)
    def fail(*args):
        raise SQLAlchemyError("Simulated notification storage failure")
    monkeypatch.setattr(service, "notify", fail)
    assert network.patch(f"/api/guidance-requests/{rid}/accept").status_code == 503
    with SessionLocal() as db:
        assert db.get(GuidanceRequest, rid).status == "PENDING"
        assert db.scalar(select(func.count()).select_from(Connection)) == 0
        assert db.scalar(select(func.count()).select_from(Notification)) == 1


@pytest.mark.parametrize("action", ["accept","reject"])
def test_terminal_response_cannot_repeat(network, action):
    rid = pending(network)
    login(network, 3)
    assert network.patch(f"/api/guidance-requests/{rid}/{action}").status_code == 200
    for followup in ("accept","reject"):
        assert network.patch(f"/api/guidance-requests/{rid}/{followup}").status_code == 409
    login(network)
    notes = network.get("/api/notifications").json()["items"]
    assert len(notes) == 1
    assert notes[0]["type"] == ("REQUEST_ACCEPTED" if action == "accept" else "REQUEST_REJECTED")


def test_rejection_cooldown_exact_boundary(network, monkeypatch):
    rid = pending(network)
    stamp = service.now()
    monkeypatch.setattr(service, "now", lambda: stamp)
    login(network, 3)
    rejected = network.patch(f"/api/guidance-requests/{rid}/reject").json()
    assert rejected["cooldown_until"]
    assert network.get("/api/connections").json()["total_results"] == 0
    login(network)
    monkeypatch.setattr(service, "now", lambda: stamp + timedelta(days=30, microseconds=-1))
    assert send(network).status_code == 409
    monkeypatch.setattr(service, "now", lambda: stamp + timedelta(days=30))
    assert send(network).status_code == 201


def test_disconnect_reactivate_unique_pair(network):
    rid, cid = accepted(network)
    login(network, 2)
    assert network.patch(f"/api/connections/{cid}/disconnect").status_code == 404
    login(network)
    assert network.patch(f"/api/connections/{cid}/disconnect").json()["status"] == "DISCONNECTED"
    newer = send(network).json()["id"]
    login(network, 3)
    assert network.patch(f"/api/guidance-requests/{newer}/accept").status_code == 200
    data = network.get("/api/connections").json()
    assert data["total_results"] == 1
    assert data["items"][0]["id"] == cid
    assert data["items"][0]["source_request_id"] == newer
    with SessionLocal() as db:
        db.add(Connection(student_user_id=1, alumni_user_id=3, status="ACTIVE", source_request_id=rid, connected_at=service.now()))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


@pytest.mark.parametrize("blocker", [1,3])
def test_block_and_unblock_owner(network, blocker):
    _, cid = accepted(network)
    login(network, blocker)
    result = network.patch(f"/api/connections/{cid}/block").json()
    assert result["blocked_by_user_id"] == blocker
    login(network)
    assert send(network).status_code == 409
    login(network, 3 if blocker == 1 else 1)
    assert network.patch(f"/api/connections/{cid}/unblock").status_code == 403
    login(network, blocker)
    assert network.patch(f"/api/connections/{cid}/unblock").json()["status"] == "DISCONNECTED"
    login(network)
    assert send(network).status_code == 201


def test_block_cancels_pending_atomically_before_connection(network):
    rid = pending(network)
    login(network, 3)
    result = network.post("/api/connections/block", json={"other_user_id":1})
    assert result.status_code == 200, result.text
    assert result.json()["connected_at"] is None
    assert network.patch(f"/api/guidance-requests/{rid}/accept").status_code == 409
    login(network)
    assert network.get("/api/guidance-requests/my").json()["items"][0]["status"] == "CANCELLED"
    assert send(network).status_code == 409


def test_private_lists_and_student_profile(network):
    rid = pending(network)
    login(network, 2)
    assert network.get("/api/guidance-requests/my?student_user_id=1").json()["total_results"] == 0
    assert network.get("/api/connections").json()["total_results"] == 0
    assert network.get("/api/guidance-requests/incoming").status_code == 403
    login(network, 4)
    assert network.get("/api/guidance-requests/incoming?alumni_user_id=3").json()["total_results"] == 0
    assert network.get(f"/api/guidance-requests/{rid}/student-profile").status_code == 404
    login(network, 3)
    profile = network.get(f"/api/guidance-requests/{rid}/student-profile").json()
    assert profile["name"] == "Person 1"
    assert "email" not in profile and "password_hash" not in profile
    assert network.get("/api/guidance-requests/my").status_code == 403


def test_notification_privacy_and_read(network):
    pending(network)
    login(network, 3)
    note = network.get("/api/notifications").json()["items"][0]
    login(network, 4)
    assert network.patch(f"/api/notifications/{note['id']}/read").status_code == 404
    assert network.get("/api/notifications").json()["total_results"] == 0
    login(network, 3)
    assert network.patch(f"/api/notifications/{note['id']}/read").json()["is_read"]
    assert network.patch(f"/api/notifications/{note['id']}/read").status_code == 200
    assert network.get("/api/notifications").json()["unread_count"] == 0


@pytest.mark.parametrize("changes", [{"message":""},{"message":"   "},{"message":"x"*1001},{"guidance_area_id":999},{"alumni_user_id":2},{"student_user_id":2}])
def test_invalid_request(network, changes):
    login(network)
    assert send(network, **changes).status_code in (404,422)


def test_pagination_and_pending_never_expires(network):
    login(network)
    for uid in range(3,6):
        assert send(network, uid).status_code == 201
    with SessionLocal() as db:
        for row in db.scalars(select(GuidanceRequest)):
            row.created_at = service.now() - timedelta(days=365)
        db.commit()
    data = network.get("/api/guidance-requests/my?page=2&page_size=2").json()
    assert data["total_results"] == 3 and data["total_pages"] == 2
    assert len(data["items"]) == 1 and data["pending_count"] == 3
    assert network.get("/api/guidance-requests/my?page_size=51").status_code == 422


def test_networking_origin_and_anonymous_protection(network):
    assert send(network).status_code == 401
    login(network)
    assert network.post("/api/guidance-requests", headers={"Origin":"https://evil.example"},
                        json={"alumni_user_id":3,"guidance_area_id":1,"message":"Help"}).status_code == 403


def test_block_cannot_probe_unrelated_private_profile(network):
    login(network, 3)
    assert network.post("/api/connections/block", json={"other_user_id":2}).status_code == 404
    assert network.get("/api/connections").json()["total_results"] == 0
