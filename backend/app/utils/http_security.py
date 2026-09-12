import hmac
import logging
import re
from uuid import uuid4
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException
from app.config import settings
from app.utils.rate_limit import limiter

log = logging.getLogger("platform.http")


class HTTPSecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        method, path = scope["method"], scope["path"]
        headers = dict(scope.get("headers", []))
        request_id = uuid4().hex
        started = False
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            if method in ("POST","PUT","PATCH","DELETE") and path != "/api/profiles/alumni/me/verification":
                consumed += len(message.get("body", b""))
                if consumed > 65536:
                    raise HTTPException(413, "Request body is too large.")
            return message

        async def secured_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                extra = [(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
                         (b"referrer-policy", b"no-referrer"), (b"x-request-id", request_id.encode())]
                if path.startswith("/api/"):
                    extra.append((b"cache-control", b"no-store"))
                if settings.ENVIRONMENT == "production":
                    extra.append((b"strict-transport-security", b"max-age=31536000"))
                existing = list(message.get("headers", []))
                names = {key.lower() for key, _ in existing}
                message["headers"] = existing + [(key,value) for key,value in extra if key not in names]
            await send(message)

        async def reject(status_code, detail, **kwargs):
            await JSONResponse({"detail":detail, **kwargs}, status_code=status_code)(scope, receive, secured_send)

        if method in ("POST","PUT","PATCH","DELETE"):
            origin = headers.get(b"origin", b"").decode("latin1")
            if (origin and origin not in settings.cors_origins) or (not origin and headers.get(b"sec-fetch-site") == b"cross-site"):
                return await reject(403, "Untrusted request origin.")
            ip = (scope.get("client") or ("unknown",))[0]
            identity = scope.get("session", {}).get("user_id") or ip
            policy = None
            if path == "/api/auth/login":
                policy = ("login", ip, settings.LOGIN_RATE_LIMIT, 60)
            elif path == "/api/auth/register":
                policy = ("register", ip, settings.REGISTER_RATE_LIMIT, 3600)
            elif path == "/api/guidance-requests" and method == "POST":
                policy = ("request", identity, settings.REQUEST_RATE_LIMIT, 60)
            elif re.fullmatch(r"/api/conversations/\d+/messages", path) and method == "POST":
                policy = ("message", identity, settings.MESSAGE_RATE_LIMIT, 60)
            if policy:
                kind, who, limit, seconds = policy
                retry = limiter.check((kind, str(who)), limit, seconds)
                if retry:
                    response = JSONResponse({"detail":"Too many attempts. Please try again shortly."}, status_code=429,
                                            headers={"Retry-After":str(retry)})
                    return await response(scope, receive, secured_send)
            expected = scope.get("session", {}).get("csrf_token", "")
            supplied = headers.get(b"x-csrf-token", b"")
            if not expected or not supplied or not hmac.compare_digest(expected.encode(), supplied):
                return await reject(403, "CSRF validation failed. Refresh and try again.", code="csrf_failed")
            if path != "/api/profiles/alumni/me/verification":
                try:
                    if int(headers.get(b"content-length", b"0")) > 65536:
                        return await reject(413, "Request body is too large.")
                except ValueError:
                    return await reject(400, "Invalid content length.")
        try:
            await self.app(scope, bounded_receive, secured_send)
        except Exception as error:
            # Exception strings/tracebacks can contain SQL parameters or private content.
            log.error("request_failed request_id=%s method=%s error_type=%s", request_id, method, type(error).__name__)
            if not started:
                await reject(500, "An unexpected server error occurred.", request_id=request_id)
            else:
                raise
