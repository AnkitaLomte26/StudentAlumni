"""PostgreSQL-only concurrency tests, using the existing disposable-schema fixture."""
import os
import pytest
from sqlalchemy import select, func
from tests.test_phase4_postgres import pg, session, parallel
from tests.test_phase4 import send
from app.models.messaging import Conversation, Message
from app.models.networking import Notification

pytestmark = pytest.mark.skipif(not os.getenv("PHASE4_TEST_DATABASE_URL"), reason="Run scripts/test_postgres.py")


def connected():
    student, alumni = session(1), session(3)
    rid = send(student).json()["id"]
    assert alumni.patch(f"/api/guidance-requests/{rid}/accept").status_code == 200
    connection = student.get("/api/connections").json()["items"][0]["id"]
    return student, alumni, connection


def test_postgres_simultaneous_open_reuses_conversation(pg):
    student, alumni, connection = connected()
    try:
        responses = parallel([lambda:student.post(f"/api/connections/{connection}/conversation"),
                              lambda:alumni.post(f"/api/connections/{connection}/conversation")])
        assert [r.status_code for r in responses] == [200,200]
        assert responses[0].json()["id"] == responses[1].json()["id"]
        with pg() as db:
            assert db.scalar(select(func.count()).select_from(Conversation)) == 1
    finally: student.close(); alumni.close()


def test_postgres_simultaneous_sends_one_unread_notification(pg):
    student, alumni, connection = connected()
    cid = student.post(f"/api/connections/{connection}/conversation").json()["id"]
    second = session(1)
    try:
        responses = parallel([lambda:student.post(f"/api/conversations/{cid}/messages",json={"content":"First"}),
                              lambda:second.post(f"/api/conversations/{cid}/messages",json={"content":"Second"})])
        assert [r.status_code for r in responses] == [201,201]
        with pg() as db:
            assert db.scalar(select(func.count()).select_from(Message)) == 2
            assert db.scalar(select(func.count()).select_from(Notification).where(Notification.type=="MESSAGE_RECEIVED")) == 1
    finally: student.close(); alumni.close(); second.close()


@pytest.mark.parametrize("action", ["block","disconnect"])
def test_postgres_send_serializes_with_connection_change(pg, action):
    student, alumni, connection = connected()
    cid = student.post(f"/api/connections/{connection}/conversation").json()["id"]
    try:
        responses = parallel([lambda:student.post(f"/api/conversations/{cid}/messages",json={"content":"Concurrent send"}),
                              lambda:alumni.patch(f"/api/connections/{connection}/{action}")])
        assert responses[0].status_code in (201,409)
        assert responses[1].status_code == 200
        assert student.post(f"/api/conversations/{cid}/messages",json={"content":"After change"}).status_code == 409
        history = student.get(f"/api/conversations/{cid}/messages")
        assert history.status_code == 200
        assert history.json()["total_results"] == (1 if responses[0].status_code==201 else 0)
    finally: student.close(); alumni.close()

