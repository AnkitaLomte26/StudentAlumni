import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.database import SessionLocal
from app.models.messaging import Conversation, Message
from app.models.networking import Notification
from app.services import messaging
from tests.test_phase4 import network, login, accepted, send


@pytest.fixture()
def chat(network):
    _, connection = accepted(network)
    response = network.post(f"/api/connections/{connection}/conversation")
    assert response.status_code == 200, response.text
    return network, connection, response.json()["id"]


def message(client, cid, content="Hello from the test participant.", **extra):
    return client.post(f"/api/conversations/{cid}/messages", json={"content":content, **extra})


def test_participants_open_same_conversation(chat):
    c, connection, cid = chat
    login(c)
    assert c.post(f"/api/connections/{connection}/conversation").json()["id"] == cid
    assert c.get(f"/api/conversations/{cid}").json()["other_participant"]["user_id"] == 3
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Conversation)) == 1
        db.add(Conversation(connection_id=connection))
        with pytest.raises(IntegrityError): db.commit()
        db.rollback()


@pytest.mark.parametrize("method,path", [
    ("get",""),("get","/messages"),("post","/messages"),("patch","/read")])
def test_nonparticipant_cannot_access_any_endpoint(chat, method, path):
    c, _, cid = chat
    login(c,2)
    kwargs = {"json":{"content":"Intrusion"}} if method=="post" else {"json":{"through_message_id":1}} if method=="patch" else {}
    assert getattr(c,method)(f"/api/conversations/{cid}{path}", **kwargs).status_code == 404
    assert c.get("/api/conversations").json()["total_results"] == 0


def test_nonparticipant_cannot_open_connection(chat):
    c, connection, _ = chat
    login(c,4)
    assert c.post(f"/api/connections/{connection}/conversation").status_code == 404


def test_both_directions_persist_and_sender_session(chat):
    c, _, cid = chat
    assert message(c,cid,"Alumni reply").json()["sender_user_id"] == 3
    login(c)
    result = message(c,cid,"Student question")
    assert result.status_code == 201
    assert result.json()["sender_user_id"] == 1
    history = c.get(f"/api/conversations/{cid}/messages").json()["items"]
    assert [m["content"] for m in history] == ["Alumni reply","Student question"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Message)) == 2
    assert "email" not in str(c.get(f"/api/conversations/{cid}").json())


def test_spoofing_rejected(chat):
    c, _, cid = chat
    assert message(c,cid,sender_user_id=1).status_code == 422
    assert message(c,cid,conversation_id=999).status_code == 422
    assert c.get(f"/api/conversations/{cid}/messages").json()["total_results"] == 0


@pytest.mark.parametrize("value", ["", "   \n\t", "x"*2001, "\x00", None, 12])
def test_content_validation(chat, value):
    c, _, cid = chat
    assert message(c,cid,value).status_code == 422


def test_html_is_plain_text_and_maximum_valid(chat):
    c, _, cid = chat
    assert message(c,cid,"<img src=x onerror=alert(1)>").json()["content"] == "<img src=x onerror=alert(1)>"
    assert message(c,cid,"x"*2000).status_code == 201


@pytest.mark.parametrize("action", ["disconnect","block"])
def test_history_after_relationship_change(chat, action):
    c, connection, cid = chat
    mid = message(c,cid).json()["id"]
    assert c.patch(f"/api/connections/{connection}/{action}").status_code == 200
    assert message(c,cid).status_code == 409
    login(c)
    assert message(c,cid).status_code == 409
    assert c.get(f"/api/conversations/{cid}/messages").json()["items"][0]["id"] == mid
    assert c.get(f"/api/conversations/{cid}").json()["can_send"] is False
    assert c.post(f"/api/connections/{connection}/conversation").json()["id"] == cid
    assert c.patch(f"/api/conversations/{cid}/read",json={"through_message_id":mid}).status_code == 200


def test_inactive_connection_cannot_create_first_conversation(network):
    c = network
    _, connection = accepted(c)
    assert c.patch(f"/api/connections/{connection}/disconnect").status_code == 200
    assert c.post(f"/api/connections/{connection}/conversation").status_code == 409


def test_reconnect_reuses_history(chat):
    c, connection, cid = chat
    mid = message(c,cid).json()["id"]
    c.patch(f"/api/connections/{connection}/disconnect")
    login(c)
    rid = send(c).json()["id"]
    login(c,3)
    assert c.patch(f"/api/guidance-requests/{rid}/accept").status_code == 200
    assert c.post(f"/api/connections/{connection}/conversation").json()["id"] == cid
    assert message(c,cid).status_code == 201
    assert c.get(f"/api/conversations/{cid}/messages").json()["items"][0]["id"] == mid


def test_snapshot_pagination_with_new_arrivals(chat):
    c, _, cid = chat
    for i in range(7): assert message(c,cid,f"Message {i}").status_code == 201
    first = c.get(f"/api/conversations/{cid}/messages?page_size=3").json()
    assert [m["content"] for m in first["items"]] == ["Message 4","Message 5","Message 6"]
    assert first["total_pages"] == 3
    message(c,cid,"New arrival")
    second = c.get(f"/api/conversations/{cid}/messages?page=2&page_size=3&snapshot_id={first['snapshot_id']}").json()
    assert [m["content"] for m in second["items"]] == ["Message 1","Message 2","Message 3"]
    assert second["total_results"] == 7
    assert c.get(f"/api/conversations/{cid}/messages?page_size=51").status_code == 422
    assert c.get(f"/api/conversations/{cid}/messages?page=0").status_code == 422
    assert c.get(f"/api/conversations/{cid}/messages?page=99").json()["items"] == []


def test_preview_notifications_coalesce_and_read_boundary(chat):
    c, _, cid = chat
    first = message(c,cid,"First").json()["id"]
    second = message(c,cid,"Second").json()["id"]
    login(c)
    data = c.get("/api/conversations").json()
    assert data["items"][0]["last_message_preview"] == "Second"
    assert data["items"][0]["unread_count"] == 2
    notes = [n for n in c.get("/api/notifications").json()["items"] if n["type"]=="MESSAGE_RECEIVED"]
    assert len(notes) == 1 and notes[0]["conversation_id"] == cid and notes[0]["request_id"] is None
    assert c.patch(f"/api/conversations/{cid}/read",json={"through_message_id":first}).json()["unread_count"] == 1
    assert c.patch(f"/api/conversations/{cid}/read",json={"through_message_id":second}).json()["unread_count"] == 0
    rows = c.get(f"/api/conversations/{cid}/messages").json()["items"]
    assert all(row["read_at"] for row in rows)
    assert c.patch(f"/api/conversations/{cid}/read",json={"through_message_id":second}).status_code == 200
    login(c,3)
    message(c,cid,"Third")
    login(c)
    notes = [n for n in c.get("/api/notifications").json()["items"] if n["type"]=="MESSAGE_RECEIVED"]
    assert len(notes) == 2 and sum(not n["is_read"] for n in notes) == 1


def test_sender_cannot_mark_own_sent_message_read(chat):
    c, _, cid = chat
    mid = message(c,cid).json()["id"]
    c.patch(f"/api/conversations/{cid}/read",json={"through_message_id":mid})
    assert c.get(f"/api/conversations/{cid}/messages").json()["items"][0]["read_at"] is None


def test_message_transaction_rollback(chat, monkeypatch):
    c, _, cid = chat
    def fail(*args): raise SQLAlchemyError("notification failure")
    monkeypatch.setattr(messaging,"message_notification",fail)
    assert message(c,cid).status_code == 503
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Message)) == 0
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.type=="MESSAGE_RECEIVED")) == 0


def test_no_message_notifications_to_sender(chat):
    c, _, cid = chat
    message(c,cid)
    assert all(n["type"]!="MESSAGE_RECEIVED" for n in c.get("/api/notifications").json()["items"])


def test_anonymous_and_cross_origin_blocked(chat):
    c, _, cid = chat
    assert c.post(f"/api/conversations/{cid}/messages",json={"content":"CSRF"},headers={"Origin":"https://evil.example"}).status_code == 403
    c.post("/api/auth/logout")
    assert message(c,cid).status_code == 401
    assert c.get(f"/api/conversations/{cid}/messages").status_code == 401


def test_inactive_recipient_cannot_receive(chat):
    from app.models import User
    c, _, cid = chat
    with SessionLocal() as db:
        db.get(User,1).account_status="DEACTIVATED"
        db.commit()
    assert message(c,cid).status_code == 409
    assert c.get(f"/api/conversations/{cid}").json()["can_send"] is False
    assert c.get(f"/api/conversations/{cid}/messages").status_code == 200


def test_foreign_read_boundary_rejected(chat):
    c, _, cid = chat
    assert c.patch(f"/api/conversations/{cid}/read",json={"through_message_id":999}).status_code == 422
    assert c.get(f"/api/conversations/{cid}/messages?snapshot_id=999").status_code == 422

