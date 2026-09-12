# Phase 6: real-time delivery and deployment

Phase 6 keeps the existing PostgreSQL schema and message service. No new tables or migration are needed; Alembic head remains `004_conversations_messages`. Previous phase documents describe their historical implementation.

## Messaging architecture

The client POSTs messages through the existing REST endpoint. The shared messaging service authenticates the sender from the signed cookie, checks participation and ACTIVE relationship/account state under the existing pair row locks, persists the message and grouped notification, and commits. Only then does the REST route publish `message.created` to connected participants. Delivery failure cannot undo a committed message. Offline users retrieve it through REST history.

`/ws/conversations/{conversation_id}` is a **delivery-only** WebSocket. Client message/identity commands are rejected; keeping sends on the existing REST endpoint avoids a second business-logic implementation and preserves HTTP CSRF/rate controls. Initial history, pagination, read updates and sends remain REST. The WebSocket transports new message events, ready and heartbeat events.

The server validates the signed session cookie, its lifetime, an exact allowed Origin, an active student/alumni account, and conversation ownership through the associated connection before accepting access. It rechecks account/ownership/session expiry before delivery and on 20-second heartbeats. Logout closes that user's live sockets. Disconnect/block preserves participants' access to history, while the REST service forbids new sends. Guessed conversation IDs never grant access.

The in-memory manager limits connections to 5 per user and 1,000 total and bounds delivery waits. Run **one Uvicorn worker / one backend instance**. Rate-limit counters and logout socket closure are also process-local.

> An in-memory connection manager is sufficient for the current single-server deployment. With multiple backend instances, WebSocket events would need shared coordination such as Redis Pub/Sub.

The browser displays Live/Connecting/reconnecting status, retries after 1, 2, 4, 8 and 16 seconds, then offers manual refresh. Authorization rejection stops automatic retries. Switching conversations/navigation closes the previous socket. A REST refresh after connection/reconnection recovers messages missed during a delivery gap. Message IDs deduplicate POST responses and events; rendering uses textContent. The latest display is bounded to 30 messages; older pages retain REST pagination. Incoming events do not interrupt an older history page. A bounded queue holds events while REST requests are processing.

A connection-state change is enforced immediately on the server. Another open browser learns the changed composer state on its next refresh/reconnect or refused send; there is no separate presence/relationship-event system.

## HTTP security

GET `/api/auth/csrf` creates a random token in the signed session (including an anonymous session before login). Every POST/PATCH/PUT/DELETE requires the matching `X-CSRF-Token`. Login rotates the session and token. The shared API helper fetches the current token and includes credentials automatically; callers do not duplicate this logic. Safe GETs need no CSRF header. Login and registration are protected too. Missing/invalid tokens return 403; failed writes are never automatically retried.

State-changing HTTP Origin headers must match the configured allowlist. WebSocket Origin is mandatory. CORS allows explicit origins, required methods and Content-Type/X-CSRF-Token headers, never credentialed wildcard origins. CORS controls browsers, not general HTTP clients; server authentication, authorization and CSRF remain authoritative.

Signed session cookies are HttpOnly. Development supports HTTP with Secure disabled; production configuration requires Secure cookies, HTTPS frontend origins, a non-placeholder secret of at least 32 characters, and explicit allowed hosts. SameSite defaults to lax; none requires Secure. Session lifetime defaults to 86,400 seconds. A signed cookie is not encrypted: only user ID and random CSRF token belong in it. Logout clears the browser cookie; this existing stateless session design does not provide a persistent server-side session-revocation registry. Keep HTTPS and secret handling strict.

Targeted fixed-window, bounded in-memory limits return 429 with Retry-After:

| Operation | Default | Key |
| --- | --- | --- |
| Login | 30/minute | client IP |
| Registration | 10/hour | client IP |
| Guidance request creation | 30/minute | session user (IP if anonymous) |
| Message sending | 120/minute | session user (IP if anonymous) |
| WebSocket connection attempts | 60/minute | client IP; refused handshake |

Counters reset on process restart. These are single-server abuse controls, not distributed quotas. Limits count attempts, including rejected requests. Accurate IP limits require correctly configured trusted reverse proxies.

The security pass preserves explicit response schemas/ownership checks, session-derived senders, validated uploads, random private proof filenames and admin-only proof retrieval. API responses are no-store. Responses receive nosniff, frame denial and no-referrer headers; production API responses add HSTS. Nginx adds a self-only Content Security Policy. Non-upload request bodies are capped at 64 KiB, including chunked bodies; existing upload guards enforce the proof-specific size/type rules.

Unexpected errors return a generic message and request ID. Logs include startup/shutdown, DB connectivity problems, error class/request ID, socket IDs, and admin verification decisions. They exclude passwords, cookies, tokens, proof/message contents and SQL parameters. This deliberately avoids logging arbitrary exception tracebacks that may contain private data.

## Endpoints added / changed

- GET `/api/auth/csrf`: CSRF handshake, no authentication required.
- WS `/ws/conversations/{id}`: authenticated participant delivery.
- GET `/readiness`: 200 when database is reachable, 503 otherwise.
- GET `/health`: application status and connected/disconnected database state, without connection details.
- Existing POST `/api/conversations/{id}/messages`: unchanged payload/response; publishes after persistence.
- Existing mutation APIs now require CSRF; logout additionally closes sockets. Existing authenticated GET contracts remain unchanged.

## Environment configuration

Copy `backend/.env.example` for local development, or root `.env.docker.example` for Compose. Never commit actual env files.

| Variable | Purpose |
| --- | --- |
| DATABASE_URL | PostgreSQL SQLAlchemy URL; URL-encode credential characters |
| SECRET_KEY | Independent random signing secret; use 32 random bytes or more |
| ENVIRONMENT | development, production or test |
| FRONTEND_ORIGIN | Comma-separated exact allowed frontend origins |
| ALLOWED_HOSTS | Comma-separated backend request hosts |
| SESSION_HTTPS_ONLY | false for local HTTP, true for HTTPS production |
| SESSION_SAME_SITE | lax by default; strict/none supported |
| SESSION_MAX_AGE | Cookie lifetime in seconds, default 86400 |
| UPLOAD_DIRECTORY | Private proof storage, never frontend/static directory |
| LOGIN_RATE_LIMIT / REGISTER_RATE_LIMIT | Limits above |
| REQUEST_RATE_LIMIT / MESSAGE_RATE_LIMIT / WS_RATE_LIMIT | Limits above |

Legacy FRONTEND_ORIGINS and VERIFICATION_STORAGE_DIR aliases remain accepted. Prefer the singular FRONTEND_ORIGIN and UPLOAD_DIRECTORY names.

`frontend/js/config.js` centralizes API configuration. On localhost/127.0.0.1 port 5500 it selects the matching host on port 8000. Other deployments default to the page origin, suitable for the Nginx proxy. Override window.APP_CONFIG there for a separate API origin and include it in the exact CORS allowlist (and adapt Nginx CSP if cross-origin). The API helper derives WS/WSS from this configuration; HTTPS pages always use WSS. No localhost URLs are scattered across callers.

## Docker startup

The three services are Nginx frontend, non-root Python backend, and PostgreSQL 16. PostgreSQL data and verification proofs have separate persistent volumes. The backend/database publish no host ports. Frontend binds localhost:8080, suitable for local development or an HTTPS reverse proxy. Build contexts exclude env files, virtualenvs, tests and private uploads. There are no baked credentials.

From project root (PowerShell):

```powershell
Copy-Item .env.docker.example .env.docker
python -c "import secrets; print(secrets.token_hex(32))"
# Generate twice: set independent POSTGRES_PASSWORD and SECRET_KEY in .env.docker.
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker build
docker compose --env-file .env.docker up -d postgres
docker compose --env-file .env.docker run --rm backend python -m alembic upgrade head
docker compose --env-file .env.docker run --rm backend python -m alembic check
docker compose --env-file .env.docker run --rm backend python -m app.cli seed-catalogs
docker compose --env-file .env.docker up -d backend frontend
docker compose --env-file .env.docker ps
```

Compose waits for PostgreSQL health before starting backend commands; backend readiness gates frontend startup. Migrations are explicit, separate commands, never an automatic action for every worker. Run them once before application startup on each release. Back up the database and proof volume before upgrades. Catalog seeding is repeatable and creates no alumni/users.

Admins cannot register through the public registration page. Create one interactively (password is prompted, never hardcoded):

```powershell
docker compose --env-file .env.docker run --rm backend python -m app.cli create-admin --name "College Administrator" --email admin@example.edu
```

The administrator logs in through the normal `login.html` page. The existing role-based redirect opens `admin.html`; public registration accepts only STUDENT or ALUMNI.

Preview http://localhost:8080, check http://localhost:8080/health and /readiness. Normal stop: `docker compose --env-file .env.docker down`; do not add `-v` unless you intentionally want to delete persistent data.

## Production

Use HTTPS at the hosting platform or reverse proxy and WSS for browser sockets. Do not implement TLS inside FastAPI. Set ENVIRONMENT=production, SESSION_HTTPS_ONLY=true, FRONTEND_ORIGIN=https://your-host, and ALLOWED_HOSTS to the public host plus internal healthcheck hosts (localhost,127.0.0.1,backend for this Compose setup). Keep secrets outside images/version control. Set the proof volume permissions so the backend user can read/write it.

The image uses this production command, with exactly one worker and no reload:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --ws-max-size 4096 --ws-max-queue 16 --no-server-header
```

Compose sets FORWARDED_ALLOW_IPS=* only because the backend port is private and Nginx overwrites client-supplied forwarded IP headers. Never use that trust setting on a publicly reachable ASGI port. For a bare-host backend, restrict FORWARDED_ALLOW_IPS to the actual reverse-proxy IP. When adding a TLS proxy ahead of Nginx, configure Nginx real_ip_header/set_real_ip_from for the exact trusted proxy CIDRs so client IP rate limits remain meaningful. Do not trust arbitrary forwarded headers.

The outer TLS proxy must forward WebSocket upgrades, allow idle connections longer than the 20-second heartbeat, forward the public Host, and apply HTTPS/HSTS to the whole site. Secure cookies are selected explicitly from environment, so HTTP between the trusted proxy and backend does not disable cookie security. Expose only the intended HTTPS entry point; keep database/backend internal.

Operational references: [Starlette session middleware](https://starlette.dev/middleware/) and [Docker Compose readiness ordering](https://docs.docker.com/compose/how-tos/startup-order/).

## Verification and limits

Run from backend:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/test_postgres.py
```

The standard suite uses isolated SQLite fixtures. PostgreSQL tests use uniquely named temporary schemas, check real constraints/row-lock concurrency, then drop only their own schemas. Set PHASE4_TEST_DATABASE_URL for a separate test database; the existing runner otherwise reads the local backend .env URL and only creates temporary schemas. Its database role needs schema-creation privileges. Frontend checks: `node --test frontend/tests/realtime.test.cjs` from project root.

Final verification completed: Alembic upgrade/check passed at `004_conversations_messages`; 130 standard tests passed (9 environment-specific tests skipped); all 9 PostgreSQL constraint/concurrency tests passed; and all 4 frontend real-time unit tests passed. This is 143 passing checks in total. `pip check` reported no broken dependencies.

Two independent browser sessions (localhost student and 127.0.0.1 alumni) displayed Live. Student send, alumni receipt without refresh, alumni reply, message-ID deduplication, and persistence across both page reloads passed. Disconnect and block disabled sending while retaining 30 visible latest-history messages; accepting a new request reused conversation 1 and all history. Registration/login, verified discovery, accept/reject, cooldown, private-proof denial, missing-CSRF rejection, notifications, pagination, and restoring the QA connection to ACTIVE also passed. Browser console logs were empty. The existing responsive CSS breakpoints and focused mobile layouts remain unchanged; the chat DOM uses flexible/grid sizing without fixed page widths.

Docker Compose configuration was validated. Docker Desktop/CLI were installed, but the local engine became unresponsive: build/image commands stalled and were cancelled. Therefore image build, container startup and end-to-end container behavior could not be verified on this machine. Run the commands above on a working Docker engine before deployment.

## Files in this phase

New backend: app/routes/realtime.py, app/services/realtime.py, app/utils/http_security.py, app/utils/rate_limit.py, tests/http_client.py, tests/test_phase6.py, Dockerfile, .dockerignore.

Changed backend: app/config.py, app/main.py, app/routes/auth.py, app/routes/messaging.py, app/routes/verification.py, requirements.txt, .env.example, tests/conftest.py, tests/test_phase4_postgres.py (real CSRF-aware test client).

New frontend: js/config.js, js/realtime.js, tests/realtime.test.cjs, Dockerfile, .dockerignore, nginx.conf.
Changed frontend: js/api.js, js/chat.js, chat.html; all other HTML entry pages load shared config before api.js.
Root: README.md, PHASE6.md, docker-compose.yml, .env.docker.example, .gitignore. Local env/QA artifacts are ignored, not distributable source.

Final pre-deployment UX pass: `login.html` and `register.html` use the shared `ui.js` password-visibility control; `admin.html`/`admin.js` provide paginated search and creation for companies, skills, and guidance areas; `professional.py` accepts backward-compatible catalog offsets and keeps admin-only creation; and `catalogs.py` includes broader idempotent skill/guidance defaults. `.gitattributes` also excludes real environment files, private uploads, QA artifacts, and local databases from `git archive`; Docker builds continue to copy only explicit application/static paths. Example environment files remain distributable placeholders.

No changes to database entities, session authentication mechanism, REST message persistence rules, frontend framework, or previous request/connection state models.
