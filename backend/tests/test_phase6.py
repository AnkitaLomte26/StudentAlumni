import pytest
from fastapi.testclient import TestClient as RawClient
from starlette.websockets import WebSocketDisconnect
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError
from unittest.mock import AsyncMock
from app.main import app
from app.database import SessionLocal
from app.models.messaging import Message
from app.config import settings, Settings
from app.services import messaging
from app.services.realtime import manager
from app.utils.rate_limit import limiter
from tests.test_phase5 import chat, message
from tests.test_phase4 import network, login

ORIGIN = {"origin":"http://testserver"}


def test_websocket_requires_authentication(chat):
    _, _, cid = chat
    with RawClient(app) as raw:
        with pytest.raises(WebSocketDisconnect):
            with raw.websocket_connect(f"/ws/conversations/{cid}", headers=ORIGIN): pass


@pytest.mark.parametrize("origin", [None,"https://evil.example"])
def test_websocket_origin_required(chat, origin):
    c, _, cid = chat
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect(f"/ws/conversations/{cid}", headers={"origin":origin} if origin else {}): pass


def test_websocket_rejects_nonparticipant(chat):
    c, _, cid = chat
    login(c,2)
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect(f"/ws/conversations/{cid}", headers=ORIGIN): pass


def test_live_delivery_to_both_after_persistence(chat):
    c, _, cid = chat
    with c.websocket_connect(f"/ws/conversations/{cid}", headers=ORIGIN) as alumni:
        assert alumni.receive_json()["type"] == "ready"
        login(c,1)
        with c.websocket_connect(f"/ws/conversations/{cid}", headers=ORIGIN) as student:
            assert student.receive_json()["type"] == "ready"
            result=message(c,cid,"A durable live message")
            assert result.status_code == 201
            for socket in (student,alumni):
                event=socket.receive_json()
                assert event["type"]=="message.created"
                assert event["message"]["id"] == result.json()["id"]
                assert event["message"]["sender_user_id"] == 1
                with SessionLocal() as db:
                    assert db.get(Message,event["message"]["id"]).content=="A durable live message"


def test_offline_recipient_uses_rest_history(chat):
    c, _, cid = chat
    mid=message(c,cid,"Offline recipient").json()["id"]
    login(c,1)
    assert c.get(f"/api/conversations/{cid}/messages").json()["items"][0]["id"]==mid


@pytest.mark.parametrize("action", ["disconnect","block"])
def test_live_socket_does_not_bypass_relationship_rules(chat, action):
    c, connection, cid=chat
    mid=message(c,cid).json()["id"]
    with c.websocket_connect(f"/ws/conversations/{cid}",headers=ORIGIN) as ws:
        assert ws.receive_json()["type"]=="ready"
        assert c.patch(f"/api/connections/{connection}/{action}").status_code==200
        assert message(c,cid).status_code==409
        assert c.get(f"/api/conversations/{cid}/messages").json()["items"][0]["id"]==mid


def test_websocket_cannot_spoof_or_send_commands(chat):
    c, _, cid=chat
    with c.websocket_connect(f"/ws/conversations/{cid}",headers=ORIGIN) as ws:
        ws.receive_json()
        ws.send_json({"type":"message.send","sender_user_id":1,"content":"Spoofed"})
        with pytest.raises(WebSocketDisconnect): ws.receive_json()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Message))==0


def test_failed_persistence_never_broadcasts(chat, monkeypatch):
    c, _, cid=chat
    publish=AsyncMock()
    monkeypatch.setattr(manager,"publish",publish)
    def fail(*args): raise SQLAlchemyError("private database detail")
    monkeypatch.setattr(messaging,"message_notification",fail)
    assert message(c,cid).status_code==503
    publish.assert_not_awaited()


def test_logout_closes_live_session(chat):
    c, _, cid=chat
    with c.websocket_connect(f"/ws/conversations/{cid}",headers=ORIGIN) as ws:
        ws.receive_json()
        assert c.post("/api/auth/logout").status_code==200
        with pytest.raises(WebSocketDisconnect): ws.receive_json()


def test_csrf_missing_wrong_and_valid(chat):
    c, _, cid=chat
    with RawClient(app,cookies=c.cookies) as raw:
        path=f"/api/conversations/{cid}/messages"
        assert raw.post(path,json={"content":"Missing"}).status_code==403
        assert raw.post(path,json={"content":"Wrong"},headers={"X-CSRF-Token":"wrong"}).status_code==403
        token=raw.get("/api/auth/csrf").json()["csrf_token"]
        assert raw.post(path,json={"content":"Valid"},headers={"X-CSRF-Token":token}).status_code==201


def test_csrf_bound_to_session_and_rotated_on_login(network):
    c=network
    with RawClient(app) as other:
        foreign=other.get("/api/auth/csrf").json()["csrf_token"]
    token=c.get("/api/auth/csrf").json()["csrf_token"]
    login(c)
    assert c.get("/api/auth/csrf").json()["csrf_token"] != token
    with RawClient(app,cookies=c.cookies) as raw:
        for bad in (token,foreign):
            assert raw.post("/api/auth/logout",headers={"X-CSRF-Token":bad}).status_code==403


def test_safe_get_and_anonymous_auth_handshake(network):
    with RawClient(app) as raw:
        assert raw.get("/health").status_code==200
        assert raw.post("/api/auth/login",json={"email":"person1@example.com","password":"TestPassword123!"}).status_code==403
        response=raw.get("/api/auth/csrf")
        assert response.headers["cache-control"]=="no-store"
        assert "httponly" in response.headers["set-cookie"].lower()
        token=response.json()["csrf_token"]
        assert raw.post("/api/auth/login",json={"email":"person1@example.com","password":"TestPassword123!"},
                        headers={"X-CSRF-Token":token}).status_code==200
        assert raw.get("/api/auth/me").status_code==200


def test_cors_allowlist(network):
    headers={"Origin":"http://testserver","Access-Control-Request-Method":"POST","Access-Control-Request-Headers":"X-CSRF-Token, Content-Type"}
    result=network.options("/api/auth/login",headers=headers)
    assert result.status_code==200
    assert result.headers["access-control-allow-origin"]=="http://testserver"
    headers["Origin"]="https://evil.example"
    result=network.options("/api/auth/login",headers=headers)
    assert result.status_code==400
    assert "access-control-allow-origin" not in result.headers


def test_login_rate_limit(network, monkeypatch):
    monkeypatch.setattr(settings,"LOGIN_RATE_LIMIT",2)
    limiter.clear()
    for _ in range(2):
        assert network.post("/api/auth/login",json={"email":"person1@example.com","password":"wrong-password"}).status_code==401
    result=network.post("/api/auth/login",json={"email":"person1@example.com","password":"wrong-password"})
    assert result.status_code==429 and int(result.headers["retry-after"])>0


def test_message_rate_limit(chat, monkeypatch):
    c, _, cid=chat
    monkeypatch.setattr(settings,"MESSAGE_RATE_LIMIT",2)
    limiter.clear()
    assert message(c,cid).status_code==201
    assert message(c,cid).status_code==201
    assert message(c,cid).status_code==429


def test_websocket_rate_limit(chat, monkeypatch):
    c, _, cid=chat
    monkeypatch.setattr(settings,"WS_RATE_LIMIT",1)
    limiter.clear()
    with c.websocket_connect(f"/ws/conversations/{cid}",headers=ORIGIN) as ws: ws.receive_json()
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect(f"/ws/conversations/{cid}",headers=ORIGIN): pass


def test_unexpected_errors_do_not_leak_content(chat, monkeypatch, caplog):
    c, _, cid=chat
    def fail(*args): raise RuntimeError("private-message-content-and-database-password")
    monkeypatch.setattr(messaging,"send_message",fail)
    result=message(c,cid)
    assert result.status_code==500
    assert "private-message" not in result.text and "private-message" not in caplog.text
    assert "request_id" in result.json()


def test_readiness_database_failure(network, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main,"check_database",lambda:"disconnected")
    assert network.get("/readiness").status_code==503
    assert network.get("/health").json()=={"status":"ok","database":"disconnected"}


def test_production_configuration_fails_closed():
    with pytest.raises(ValidationError):
        Settings(_env_file=None,DATABASE_URL="sqlite://",SECRET_KEY="short",ENVIRONMENT="production")
    valid=Settings(_env_file=None,DATABASE_URL="sqlite://",SECRET_KEY="a"*40,ENVIRONMENT="production",
                   FRONTEND_ORIGIN="https://alumni.example.edu",SESSION_HTTPS_ONLY=True,ALLOWED_HOSTS="alumni.example.edu")
    assert valid.SESSION_HTTPS_ONLY
    with pytest.raises(ValidationError):
        Settings(_env_file=None,DATABASE_URL="sqlite://",SECRET_KEY="a"*40,FRONTEND_ORIGIN="*")


def test_large_json_body_rejected(chat):
    c, _, cid=chat
    assert c.post(f"/api/conversations/{cid}/messages",json={"content":"x"*70000}).status_code==413


def test_chunked_body_limit(chat):
    c, _, cid=chat
    chunks=iter([b'{"content":"', b'x'*70000, b'"}'])
    assert c.post(f"/api/conversations/{cid}/messages",content=chunks,headers={"Content-Type":"application/json"}).status_code==413
