# Phase 4: guidance requests and connections

Phase 4 adds durable guidance requests, relationship state, and event notifications. It does not add conversations, messages, real-time transport, or Phase 5 behavior.

## State and business rules

A request is `PENDING`, `ACCEPTED`, `REJECTED`, or `CANCELLED`. Only its student can cancel it and only its recipient alumni can accept or reject it. Terminal states cannot be changed. Pending requests do not expire automatically.

A student may have at most five pending requests. The recipient must be an active, verified alumni who is accepting requests, both accounts must be active, the pair must not already be connected or blocked, and the pair must not already have a pending request. A rejection creates a 30-day pair-specific cooldown based on `responded_at`; cancellation does not.

A connection is `ACTIVE`, `DISCONNECTED`, or `BLOCKED`. Acceptance creates one or reactivates its existing disconnected row. Either participant can disconnect or block. Blocking before a connection requires an existing request between the pair; it creates a historical blocked relationship and cancels pending requests in the same transaction. This restriction prevents probing unrelated users' private profiles. Only the blocker can unblock; unblocking produces a disconnected relationship, so accepting a later request is still required to reconnect.

An alumni may accept a request already received after turning request availability off, but the alumni account must still be active and verified. The guidance area must exist in the shared catalog; it does not have to be one of the alumni's selected profile topics.

## Transaction and concurrency design

Every request or connection mutation locks the student profile first, then the alumni profile, and then the two user rows in ID order. This single order avoids pair lock inversions. Serializing mutations through the student's locked profile makes the pending-count check safe against simultaneous sends. The transaction then checks the count and writes the request plus its notification atomically.

Acceptance locks the pair, re-reads the pending request after acquiring the lock, changes it to accepted, creates or reactivates the connection, checks database integrity with a flush, and creates the notification before one commit. An error rolls the whole operation back.

The application-level duplicate check gives a useful 409 response. The partial unique index `uq_pending_request_pair` on `(student_user_id, alumni_user_id) WHERE status = 'PENDING'` is the final PostgreSQL integrity guard.

## Database

Migration `003_guidance_connections` creates:

- `guidance_requests`
- `connections`
- `notifications`

Constraints enforce request and connection state shapes, one connection per student/alumni pair, notification event uniqueness, foreign keys to the correct profile roles, and a composite source-request foreign key proving that a connection's source request belongs to the same pair.

Indexes support incoming/outgoing status history, rejection cooldown lookup, alumni connection status lists, unread notification lists, and pending-pair uniqueness. They correspond to API filters and transaction checks rather than indexing every field.

| Index / unique key | Purpose |
| --- | --- |
| `uq_pending_request_pair` | At most one pending request for the pair; partial unique index |
| `ix_request_student_status_created` | Student pending quota and outgoing status/history lists |
| `ix_request_alumni_status_created` | Incoming requests by alumni/status |
| `ix_request_pair_rejection` | Latest rejection timestamp for a pair; partial index |
| `uq_connection_pair` | One current relationship per pair; also student-prefix lookup |
| `ix_connection_alumni_status` | Alumni relationship/status lookup |
| `ix_notification_user_read_created` | Own notification list and unread count |
| `uq_notification_event` | One notification per recipient/request/event |
| `uq_request_id_pair` | Referenced unique key for the connection's composite source-request foreign key |

## API

- `POST /api/guidance-requests`
- `GET /api/guidance-requests/my`
- `GET /api/guidance-requests/incoming`
- `GET /api/guidance-requests/{id}/student-profile`
- `PATCH /api/guidance-requests/{id}/cancel|accept|reject`
- `GET /api/connections`
- `POST /api/connections/block`
- `PATCH /api/connections/{id}/disconnect|block|unblock`
- `GET /api/notifications`
- `PATCH /api/notifications/{id}/read`

Lists use page/page_size pagination with a maximum page size of 50. Request and connection responses expose limited profile summaries and never expose email, password data, session data, or verification proof.

## Frontend

- `send-request.html` validates and sends a catalog-backed guidance request.
- `requests.html` adapts to the logged-in role and shows request history/actions.
- `connections.html` shows relationship state with disconnect/block/unblock actions.
- `notifications.html` shows persistent request events and read state.
- Search results and alumni profile pages link to the request form when availability is on.
- Dashboards link to the live Phase 4 sections.

All actions use the existing `api()` wrapper with `credentials: "include"`, avoid duplicate submissions, render user data using `textContent`, display API errors, and preserve keyboard focus and live status feedback.

## Run and verify

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/test_postgres.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

The normal test suite is isolated in SQLite. `scripts/test_postgres.py` resolves the configured PostgreSQL URL, creates a randomly named temporary schema for each locking/integrity test, and drops it after the test. Set `PHASE4_TEST_DATABASE_URL` to override the local development database connection used only as the host for those temporary schemas.

From `frontend`:

```powershell
python -m http.server 5500
```

Open `http://localhost:5500`. The backend CORS configuration must include that exact origin.

## Files created or changed

Created:

- `backend/app/models/networking.py`
- `backend/app/schemas/networking.py`
- `backend/app/services/networking.py`
- `backend/app/routes/networking.py`
- `backend/migrations/versions/003_guidance_connections.py`
- `backend/tests/test_phase4.py`
- `backend/tests/test_phase4_postgres.py`
- `backend/scripts/test_postgres.py`
- `frontend/send-request.html`, `frontend/requests.html`, `frontend/connections.html`, `frontend/notifications.html`
- `frontend/js/networking.js`
- `PHASE4.md`

Updated:

- `backend/app/models/__init__.py`, `backend/app/config.py`, `backend/app/main.py`, `backend/.env.example`
- `frontend/js/api.js`, `frontend/js/professional-ui.js`, `frontend/css/style.css`
- `frontend/student-dashboard.html`, `frontend/alumni-dashboard.html`, `frontend/find-alumni.html`, `frontend/alumni-profile.html`
- `frontend/index.html`, `frontend/login.html`, `frontend/register.html`
- `README.md`

Existing API contracts and session authentication were preserved. The shared API wrapper now also formats array-shaped validation errors. No runtime dependency or frontend framework was added.

## Verification results (2026-09-02)

- Migration applied to local PostgreSQL; current revision is `003_guidance_connections`.
- `alembic check`: no new upgrade operations detected.
- Normal suite: **80 passed, 5 skipped**. The five skips are the explicitly opt-in PostgreSQL tests.
- PostgreSQL suite: **5 passed**. Total: **85 passing tests**, including all 47 existing Phase 1–3 tests.
- Concurrent seven-send test: exactly five requests accepted. Same-pair race: one created. Double acceptance: one connection and one acceptance notification. Block/send race: blocked relationship and no pending request. PostgreSQL foreign-key and pair constraints checked directly.
- Fault injection after acceptance flush: request, connection, and notification changes rolled back.
- Browser: student/alumni login, send, incoming/outgoing views, student profile dialog, accept, connection visible to both, cancel, reject, cooldown denial, disconnect, block, blocked-request denial, unblock, notification creation, and mark-read passed.
- Request history and connections checked at 390px and 320px with no horizontal overflow; native accessible confirmation/profile dialogs work.
- JavaScript syntax and HTML ID/label checks passed. Final browser console inspection showed no logged errors.
- Backend `/health`: database connected; API version `0.4.0`.
- Phase 3 browser regression: Microsoft + Backend + Electrical Engineering returned the verified alumni with “Previously at Microsoft”; existing search tests also passed.

The existing development QA accounts were used for browser checks. Their three request-history entries remain (accepted, cancelled, rejected). Their relationship was unblocked and left disconnected; the rejected pair retains its real cooldown until October 2, 2026. No history was deleted or clock changed. The five-request limit and elapsed-cooldown cases were tested in isolated automated tests rather than creating extra demo alumni.

Notifications are refreshed on demand; no polling worker, email, push service, or messaging feature was added. College verification continues to mean college identity only, not employment verification. The local directory has no Git repository metadata, so the file inventory above describes the implementation changes rather than a Git diff.
