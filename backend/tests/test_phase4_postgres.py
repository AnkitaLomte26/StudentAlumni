"""Real PostgreSQL locking checks. Every test owns an isolated, disposable schema."""
import os
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
from tests.http_client import TestClient
from sqlalchemy import create_engine, event, select, func, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from app.database import Base, get_db
from app.main import app
from app.models import User, StudentProfile, AlumniProfile
from app.models.professional import GuidanceArea
from app.models.networking import GuidanceRequest, Connection, Notification
from app.utils.security import hash_password
from tests.test_phase4 import login, send

pytestmark = pytest.mark.skipif(not os.getenv("PHASE4_TEST_DATABASE_URL"), reason="Run scripts/test_postgres.py for isolated PostgreSQL checks")


@pytest.fixture()
def pg():
    url = os.environ["PHASE4_TEST_DATABASE_URL"]
    schema = "phase4_test_" + uuid4().hex
    assert re.fullmatch(r"phase4_test_[0-9a-f]{32}", schema)
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, pool_size=12)
    @event.listens_for(engine, "connect")
    def search_path(connection, _):
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
        connection.commit()
    factory = sessionmaker(bind=engine, autoflush=False)
    try:
        Base.metadata.create_all(engine)
        with factory() as db:
            hashed = hash_password("TestPassword123!")
            for uid in range(1,11):
                role = "STUDENT" if uid <= 2 else "ALUMNI"
                db.add(User(id=uid,name=f"Person {uid}",email=f"person{uid}@example.com",password_hash=hashed,role=role,account_status="ACTIVE"))
                db.flush()
                db.add(StudentProfile(user_id=uid) if role == "STUDENT" else AlumniProfile(user_id=uid,verification_status="VERIFIED",accepting_guidance_requests=True))
            db.add(GuidanceArea(id=1,name="Career Guidance"))
            db.commit()
        def database():
            with factory() as db:
                yield db
        app.dependency_overrides[get_db] = database
        yield factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
        # Schema name is generated here, regex checked, and never supplied by a user.
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def session(uid):
    client = TestClient(app)
    login(client, uid)
    return client


def parallel(jobs):
    barrier = Barrier(len(jobs))
    def run(job):
        barrier.wait(timeout=15)
        return job()
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        return list(executor.map(run, jobs))


def test_postgres_simultaneous_seven_requests_cap_at_five(pg):
    clients = [session(1) for _ in range(7)]
    try:
        results = parallel([lambda c=c, uid=uid: send(c,uid).status_code for c,uid in zip(clients,range(3,10))])
        assert sorted(results) == [201]*5 + [409]*2
        with pg() as db:
            assert db.scalar(select(func.count()).select_from(GuidanceRequest).where(GuidanceRequest.status=="PENDING")) == 5
    finally:
        for c in clients: c.close()


def test_postgres_same_pair_concurrent_and_database_constraint(pg):
    clients = [session(1),session(1)]
    try:
        assert sorted(parallel([lambda c=c: send(c).status_code for c in clients])) == [201,409]
        with pg() as db:
            db.add(GuidanceRequest(student_user_id=1,alumni_user_id=3,guidance_area_id=1,message="Bypass app",status="PENDING"))
            with pytest.raises(IntegrityError): db.commit()
            db.rollback()
    finally:
        for c in clients: c.close()


def test_postgres_accept_twice_one_connection_and_notification(pg):
    student = session(1)
    rid = send(student).json()["id"]
    clients = [session(3),session(3)]
    try:
        results = parallel([lambda c=c: c.patch(f"/api/guidance-requests/{rid}/accept").status_code for c in clients])
        assert sorted(results) == [200,409]
        with pg() as db:
            assert db.scalar(select(func.count()).select_from(Connection)) == 1
            assert db.scalar(select(func.count()).select_from(Notification).where(Notification.type=="REQUEST_ACCEPTED")) == 1
    finally:
        student.close()
        for c in clients: c.close()


def test_postgres_block_racing_request_leaves_no_pending(pg):
    student, alumni = session(1), session(3)
    try:
        rid = send(student).json()["id"]
        assert student.patch(f"/api/guidance-requests/{rid}/cancel").status_code == 200
        results = parallel([lambda: send(student).status_code,
                            lambda: alumni.post("/api/connections/block",json={"other_user_id":1}).status_code])
        assert results[0] in (201,409) and results[1] == 200
        with pg() as db:
            assert db.scalar(select(Connection.status)) == "BLOCKED"
            assert db.scalar(select(func.count()).select_from(GuidanceRequest).where(GuidanceRequest.status=="PENDING")) == 0
    finally:
        student.close(); alumni.close()


def test_postgres_foreign_keys_and_source_pair(pg):
    student = session(1)
    rid = send(student).json()["id"]
    try:
        with pg() as db:
            db.add(GuidanceRequest(student_user_id=999,alumni_user_id=3,guidance_area_id=1,message="Invalid",status="PENDING"))
            with pytest.raises(IntegrityError): db.commit()
            db.rollback()
            from app.services.networking import now
            db.add(Connection(student_user_id=2,alumni_user_id=3,source_request_id=rid,status="ACTIVE",connected_at=now()))
            with pytest.raises(IntegrityError): db.commit()
            db.rollback()
    finally: student.close()
