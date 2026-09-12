# Student–Alumni Networking Platform

AlumniConnect helps students find verified college alumni by company, professional background, skills and guidance interests, then request career guidance and communicate privately after connecting.

Phases 1–6 are implemented. Phase 6 adds live message delivery, CSRF protection, targeted rate limits, operational health/logging, and Docker/deployment configuration. PostgreSQL remains the source of truth. Docker configuration validates, but runtime verification is pending because the local Docker engine stalled.

**Current architecture, security, environment configuration, deployment commands, file inventory and verification:** [PHASE6.md](PHASE6.md).

**Final password controls, admin catalog management, distribution checks, and updated regression results:** [PREDEPLOYMENT_UX.md](PREDEPLOYMENT_UX.md).

## Core features and architecture

- Student/alumni accounts, role-based profiles and admin college-ID verification with private proof storage.
- Combined paginated alumni discovery, work experience, skills and guidance catalogs.
- Guidance requests with pending limits/cooldowns, transactional acceptance, connections, disconnect/block and notifications.
- Persistent private messages, paginated history, read state and live WebSocket delivery.
- Responsive, accessible HTML/CSS/vanilla JavaScript frontend.

```text
HTML / CSS / JavaScript client
             ↓
      REST + WebSocket
             ↓
   FastAPI modular backend
             ↓
   SQLAlchemy / Alembic
             ↓
         PostgreSQL
```

REST handles authentication, profiles, discovery, requests, connections, message creation, history and pagination. WebSockets deliver newly committed message events. Offline recipients load persisted history later.

PostgreSQL provides relational integrity for users and relationships. Application checks give useful errors; database constraints and row-lock transactions protect against concurrent conflicts. Signed sessions fit this browser application without a separate token system. Argon2 protects stored passwords against guessing. A modular single backend keeps operations understandable; Redis, Kafka and microservices are unnecessary at the current scale. Run exactly one backend worker for the in-memory delivery and rate-limit design.

**Phase 5 setup, schema, authorization, APIs, and verification:** [PHASE5.md](PHASE5.md).

**Phase 4 setup, APIs, transaction design, files, and verification:** [PHASE4.md](PHASE4.md).

**Phase 3 setup, APIs, indexes, file list, and verification results:** [PHASE3.md](PHASE3.md).

- **Frontend:** HTML, CSS, vanilla JavaScript (not served by FastAPI)
- **Backend:** FastAPI
- **Database:** PostgreSQL
- **ORM / migrations:** SQLAlchemy + Alembic
- **Auth:** signed session cookie (not JWT)
- **Passwords:** Argon2 (`argon2-cffi`)

## Prerequisites

- Python 3.11 or newer
- PostgreSQL 14 or newer
- A browser

## Expected ports

| Service | URL |
| --- | --- |
| Backend (FastAPI / Uvicorn) | http://localhost:8000 |
| Health check | http://localhost:8000/health |
| Frontend (static server) | http://localhost:5500 |
| Register | http://localhost:5500/register.html |
| Login | http://localhost:5500/login.html |

## Backend setup

From the `backend` directory:

### 1. Virtual environment

**Windows (PowerShell):**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. PostgreSQL database

```sql
CREATE DATABASE student_alumni;
```

### 4. Environment variables

```bash
copy .env.example .env
```

Set `DATABASE_URL` to your local credentials and set `SECRET_KEY` to a long random string. Do not commit `.env`.

```
DATABASE_URL=postgresql+psycopg2://USERNAME:PASSWORD@localhost:5432/student_alumni
SECRET_KEY=replace-with-a-long-random-string
SESSION_HTTPS_ONLY=false
SESSION_SAME_SITE=lax
FRONTEND_ORIGIN=http://localhost:5500,http://127.0.0.1:5500
ENVIRONMENT=development
ALLOWED_HOSTS=localhost,127.0.0.1
```

`SESSION_HTTPS_ONLY` must stay `false` for local `http://` development. For HTTPS production, set it to `true`.

### 5. Run migrations

```bash
alembic upgrade head
alembic check
```

This creates `users`, `student_profiles`, and `alumni_profiles`. Do not create those tables by hand.
Later migrations create the professional-profile/catalog/verification, guidance-request/connection/notification, and conversation/message tables. Phase 6 needs no additional schema change. After upgrading, run `python -m app.cli seed-catalogs` from `backend`; it is safe to repeat and creates no users.

Admins cannot register through the public registration page. Create one with `python -m app.cli create-admin --name "College Administrator" --email admin@example.edu`; the command prompts privately for a password. The administrator logs in through the normal `frontend/login.html` page, and the role-based redirect opens `frontend/admin.html`.

### 6. Start FastAPI

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 7. Run tests

Standard tests use isolated SQLite fixtures. The PostgreSQL runner uses uniquely named temporary schemas for real integrity and concurrency checks; configure PHASE4_TEST_DATABASE_URL for a dedicated database (see PHASE6.md).

```bash
pytest
python scripts/test_postgres.py
```

## Frontend setup

Second terminal:

```bash
cd frontend
python -m http.server 5500
```

Open http://localhost:5500

On Windows you can also use the existing backend virtual environment without activating it:

```powershell
cd frontend
..\backend\.venv\Scripts\python.exe -m http.server 5500 --bind 127.0.0.1
```

Keep the backend running on port 8000. The shared configuration selects a matching localhost/127.0.0.1 API hostname for cookie sessions. Serve pages over HTTP rather than opening files directly. No frontend install/build step is needed. Optional frontend unit tests: `node --test frontend/tests/realtime.test.cjs` from project root.

1. Register a **Student** on `register.html`
2. Login → student dashboard
3. Logout
4. Register an **Alumni**
5. Login → alumni dashboard

`fetch()` calls use `credentials: "include"`. The shared API helper retrieves a session-bound CSRF token and includes X-CSRF-Token on mutations, including login/register. WebSockets authenticate with the same signed cookie and validate Origin plus conversation participation. Production requires HTTPS/WSS and Secure cookies; follow the explicit migration and Docker startup procedure in PHASE6.md.

## Phase 2.5 frontend

- Shared colors, spacing, typography, cards, buttons, and breakpoints live in `frontend/css/style.css`.
- `frontend/js/ui.js` handles accessible field errors and submit states.
- `frontend/js/dashboard.js` shares profile presentation between the two role-specific entry scripts. The existing endpoints and payloads remain unchanged.
- Profile completion counts only saved background fields (4 for students, 3 for alumni); no sample activity statistics are displayed.
- Alumni availability is saved with **Save profile**. Verification badges display the status returned by the existing API.
- Phase 5 adds persistent messaging; Phase 6 delivers new messages live. History remains available after disconnect/block, while sending is forbidden.
- No external fonts or frontend frameworks are used. The backend adds the websockets transport dependency for Uvicorn.

See [FRONTEND_QA.md](FRONTEND_QA.md) for the changed files, verification results, and remaining test scope.

## API

| Method | Path | Auth |
| --- | --- | --- |
| GET | `/health` | none |
| GET | `/readiness` | none |
| GET | `/api/auth/csrf` | anonymous or authenticated session |
| WS | `/ws/conversations/{id}` | active account, participant session and allowed Origin |
| POST | `/api/auth/register` | anonymous CSRF session (STUDENT or ALUMNI only) |
| POST | `/api/auth/login` | anonymous CSRF session |
| POST | `/api/auth/logout` | authenticated session + CSRF |
| GET | `/api/auth/me` | session |
| GET/PUT | `/api/profiles/student/me` | STUDENT |
| GET/PUT | `/api/profiles/alumni/me` | ALUMNI |

`/api/auth/me` never returns `password_hash`.
