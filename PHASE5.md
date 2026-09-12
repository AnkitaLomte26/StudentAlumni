# Phase 5 — persistent private REST messaging

Phase 5 adds private two-person conversations to existing student/alumni connections. Cookie session authentication, REST/JSON, FastAPI, SQLAlchemy, PostgreSQL, and the vanilla frontend remain unchanged. Delivery uses explicit manual refresh. No Phase 6 infrastructure or real-time features were added.

## Schema and migration

Migration: `backend/migrations/versions/004_conversations_messages.py`, following `003_guidance_connections`.

- `conversations`: id, connection_id (required FK to connections), created_at, updated_at. Unique `connection_id` means one conversation per relationship; participants are derived from the connection.
- `messages`: id, conversation_id, sender_user_id, content (1–2,000 characters), created_at, nullable read_at. No duplicated participant/name columns.
- Existing `notifications`: request_id becomes nullable and conversation_id is added. A target CHECK requires request events to reference a request and message events to reference a conversation. Existing request notifications are preserved.

Foreign keys use RESTRICT so related history cannot accidentally disappear through a delete. There are no message deletion/edit APIs in this phase. Downgrading the migration deliberately removes Phase 5 history and its notifications; it is not a routine operation.

| Constraint/index | Reason |
| --- | --- |
| uq_conversation_connection | Final database protection against duplicate conversations |
| ck_message_content | Required nonblank bounded content |
| ix_message_conversation_created (conversation_id, created_at, id) | History lookup, ordered with an ID tie-breaker |
| ix_message_conversation_unread | Partial index on unread messages for conversation/recipient calculations |
| uq_unread_conversation_notification | Partial unique recipient/conversation index for unread message notifications |
| ck_notification_type / ck_notification_target | Valid event kinds and the appropriate request/conversation reference |

## Creation, authorization, and transactions

A participant explicitly opens an ACTIVE connection with `POST /api/connections/{id}/conversation`. The backend creates its conversation if needed, or returns the existing conversation. Existing conversations can also be opened after disconnect/block.

Every conversation, history, send, and read endpoint resolves ownership through the associated connection. Outsiders get 404; there is no admin bypass to private conversations. History remains readable for authenticated participants in ACTIVE, DISCONNECTED, and BLOCKED states. Sending requires ACTIVE status and both accounts active. Reconnecting reuses the same connection and therefore the same conversation/history.

The sender is taken only from the authenticated session. POST accepts only content; supplying sender_user_id or conversation_id in the body returns 422. Input is trimmed, bounded, and rejects null characters. The frontend renders content using textContent, never HTML.

Conversation creation, sending, and read updates reuse Phase 4's lock order: student profile, alumni profile, participant user rows. Connection state is re-read after locking. A block/disconnect therefore serializes with sending. Message insertion, conversation activity update, and notification creation/update commit together; a failure rolls everything back.

## APIs

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | /api/connections/{id}/conversation | Idempotently open/create an authorized conversation |
| GET | /api/conversations | Own conversation summaries, paginated |
| GET | /api/conversations/{id} | Summary, other participant, status, can_send |
| GET | /api/conversations/{id}/messages | Paginated message history |
| POST | /api/conversations/{id}/messages | Send content from the session user |
| PATCH | /api/conversations/{id}/read | Acknowledge received messages through an observed message ID |

Conversation summaries include a 160-character last-message preview, activity time, basic academic profile, connection status, and unread count. No email, password hash, verification proof, or session fields are exposed.

History defaults to 30 messages per page, maximum 50. Page 1 contains the newest messages; each page is returned in chronological order. The response includes page, page_size, total_results, total_pages, and snapshot_id. Subsequent pages can pass that snapshot ID to prevent newly arriving messages shifting older pages. Refresh starts a new snapshot. Conversation lists default to 20 and cap at 50.

## Read state and notifications

The read endpoint accepts `{"through_message_id":123}`. That message must belong to the authorized conversation. Only received messages at or below that ID are marked read. A later arrival stays unread. The frontend acknowledges through the newest displayed message, treating the conversation as read through that point, including earlier history.

Sending creates “New message from <name>” in the existing notifications system. Multiple unread messages to the same recipient/conversation refresh one unread notification rather than adding one for every message. Once read, a later message may create a new notification. Reading the conversation clears its notification when no received unread messages remain. Dismissing a notification alone does not pretend the messages were read.

## Frontend

`chat.html` has a conversation list, message history, older/newer page controls, manual refresh, read badges, and a bounded composer. Outgoing and incoming bubbles are visually distinct. Desktop uses two columns; mobile stacks the conversation list above the chat.

Connection cards offer “Open conversation” for active pairs, or “View messages” when history exists. Disconnected/blocked conversations retain visible history and show an explanatory notice with a disabled composer. If the state changes while a page is open, a rejected send preserves the draft and refreshes the state.

Labels, keyboard controls, live status feedback, visible focus, and safe text rendering are preserved. Sending disables controls while processing. Drafts remain in memory when switching conversations.

## Files created

- backend/app/models/messaging.py
- backend/app/schemas/messaging.py
- backend/app/services/messaging.py
- backend/app/routes/messaging.py
- backend/migrations/versions/004_conversations_messages.py
- backend/tests/test_phase5.py
- backend/tests/test_phase5_postgres.py
- frontend/chat.html
- frontend/js/chat.js
- PHASE5.md

## Existing files changed

- backend/app/models/__init__.py
- backend/app/models/networking.py
- backend/app/schemas/networking.py
- backend/app/services/networking.py
- backend/app/main.py
- backend/scripts/test_postgres.py
- frontend/css/style.css
- frontend/js/networking.js
- frontend/student-dashboard.html, alumni-dashboard.html, alumni-profile.html, find-alumni.html
- frontend/connections.html, requests.html, send-request.html, notifications.html
- frontend/index.html
- README.md

Existing request/profile/auth endpoints keep their behavior. Connection responses add a nullable conversation_id. Notification responses add conversation_id and allow request_id=null for message events. No new package dependency was required.

## Commands

From backend:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/test_postgres.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

From frontend in a second terminal:

```powershell
python -m http.server 5500
```

Visit http://localhost:5500/chat.html after logging in, or open Messages from an accepted connection. The PostgreSQL runner uses disposable, randomly named schemas and never clears application tables. Its existing PHASE4_TEST_DATABASE_URL override also applies to Phase 5 tests.

## Scope and assumptions

Messages are text only. No attachments, presence, typing indicators, reactions, group chats, queues, push/email delivery, or WebSockets. Message arrival and remote read status become visible on manual refresh. New messages are blocked when either account is inactive, while an active participant can still read historical messages.

## Verification results — 2026-09-02

- Migration applied to local PostgreSQL; `alembic check` reports no new upgrade operations.
- Standard suite: **107 passed, 9 skipped**. Skips are the opt-in PostgreSQL tests.
- PostgreSQL suite: **9 passed**, including the five existing Phase 4 checks and four new messaging checks. **116 tests passed across both suites**, preserving all 85 Phase 1–4 tests.
- PostgreSQL concurrency checks cover simultaneous conversation creation, simultaneous sends with one grouped notification, and sends racing with disconnect/block.
- Message transaction fault injection verifies rollback when notification persistence fails.
- Browser verification: connected student opens a conversation and sends; alumni sees an unread preview, reads, and replies; both messages remain visible.
- A dedicated FastAPI process on port 8001 was started, read the stored message, terminated, restarted, and read the same conversation/message IDs and content from PostgreSQL. That temporary process was stopped afterward.
- Disconnect and block were exercised in the UI and API: history stayed readable, composer was disabled, and direct sends returned 409.
- Reconnection through a new guidance request/acceptance reused the existing conversation/history. The QA connection was ultimately restored ACTIVE.
- Thirty-one labelled pagination QA notes plus the original two-message exchange exercised 30-message pages, older/newer controls, chronological order, and retained history.
- A different student received 404 for the private detail/history/send endpoints, and their conversation list stayed empty.
- Phase 3 combined company/domain/branch discovery passed; Phase 4 send/accept/reconnect APIs passed during the same live workflow.
- Desktop (1280px) and mobile (390px) had no horizontal overflow. The mobile older page starts at its first message and retains the disabled composer when blocked.
- JavaScript syntax checks and chat HTML ID/label checks passed. Final browser console inspection reported no errors.

The fresh `Phase5 Student` QA account and 33 test messages remain for local preview, with one grouped unread message notification for the alumni. Existing Phase 4 QA history/cooldown was not reset. Local QA metadata, restart helper, and restart log are under the ignored `backend/.private/` directory. No administrator credentials or new alumni accounts were seeded.
