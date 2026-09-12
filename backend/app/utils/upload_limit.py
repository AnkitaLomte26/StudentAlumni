from fastapi import HTTPException
from starlette.responses import JSONResponse
from app.services.verification import MAX_PROOF_BYTES


class UploadLimitMiddleware:
    """Bound multipart traffic before parsing; includes a small framing allowance."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or scope.get("path") != "/api/profiles/alumni/me/verification":
            return await self.app(scope, receive, send)
        limit = MAX_PROOF_BYTES + 64 * 1024
        headers = dict(scope.get("headers", []))
        try:
            oversized = int(headers.get(b"content-length", b"0")) > limit
        except ValueError:
            oversized = True
        if oversized:
            return await JSONResponse({"detail": "College ID proof must be at most 5 MB."}, status_code=413)(scope, receive, send)
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > limit:
                raise HTTPException(413, "College ID proof must be at most 5 MB.")
            return message
        await self.app(scope, bounded_receive, send)
