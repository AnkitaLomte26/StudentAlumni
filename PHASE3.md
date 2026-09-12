# Phase 3: alumni verification and discovery

## Scope and compatibility

HTML, centralized CSS, vanilla JavaScript, REST/JSON, FastAPI, SQLAlchemy, PostgreSQL, and Alembic remain the architecture. Existing registration, session-cookie authentication, role authorization, and profile endpoints keep their contracts. The frontend API helper additionally supports multipart FormData and an ADMIN dashboard redirect.

No guidance-request, connection, conversation, message, notification, WebSocket, Redis, Docker, JWT, frontend framework, deployment, or microservice functionality was added.

This is a single-college installation: existing users have no college entity or tenant identifier. The UI does not invent a college name. Verification means an administrator approved college-alumni identity, not employment history or skills.

## Exact local commands (PowerShell)

From the project directory:

```powershell
cd C:\Users\ankit\Desktop\FIRSTONE\student-alumni-platform\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.cli seed-catalogs
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd C:\Users\ankit\Desktop\FIRSTONE\student-alumni-platform\frontend
..\backend\.venv\Scripts\python.exe -m http.server 5500 --bind 127.0.0.1
```

Open [the frontend](http://localhost:5500), [API docs](http://localhost:8000/docs), or [health](http://localhost:8000/health). Use localhost consistently for frontend and backend cookie requests. Do not run a second server if the expected port is already occupied by the existing development server.

The existing backend .env still supplies DATABASE_URL, SECRET_KEY and CORS/session configuration. Optional VERIFICATION_STORAGE_DIR defaults to an absolute backend/private_uploads directory. Never place it inside frontend; the storage code rejects that location.

### Create a local administrator

```powershell
cd C:\Users\ankit\Desktop\FIRSTONE\student-alumni-platform\backend
.\.venv\Scripts\python.exe -m app.cli create-admin --name "College Administrator" --email "admin@your-college.example"
```

Use your intended email address. The command prompts twice for a password without echoing it. It applies existing password validation and Argon2 hashing, does not overwrite/promote an existing email, and contains no default admin credentials. Public ADMIN registration remains rejected. Log in through the normal login page; administrators are redirected to admin.html.

## Migration and tables

Migration: backend/migrations/versions/002_professional_discovery.py

Revision 002_professional_discovery follows 001_users_profiles. Production/local PostgreSQL tables are created only through Alembic.

| New table | Purpose and constraints |
| --- | --- |
| companies | Reusable unique company names and creation timestamp |
| work_experience | Multiple jobs per alumni profile; company FK; role/domain; start/end dates; end >= start check |
| skills | Reusable unique skill names |
| user_skills | Composite PK (user_id, skill_id); shared by students and alumni; no role column |
| guidance_areas | Reusable unique predefined guidance topics |
| alumni_guidance_areas | Composite PK (alumni_user_id, guidance_area_id) |
| alumni_verification | One current submission/decision record per alumni; private filename/type, submission/review times, reviewer, rejection reason |

Company, skill, and guidance names are trimmed and whitespace-normalized on creation. Case-insensitive unique indexes prevent Microsoft/microsoft duplicates. Seeds look up existing normalized names and use generated IDs rather than assuming fixed IDs. No alumni users are seeded.

Work start/end dates must be valid dates between 1950 and today; end cannot precede start. A null end date represents current employment. There is no duplicated current-company field. Only alumni may manage their own work or guidance areas; work ownership is checked for updates and deletes.

### Indexes and rationale

| Index | Query or constraint served |
| --- | --- |
| uq_companies_name_ci, uq_skills_name_ci, uq_guidance_areas_name_ci | Case-insensitive name uniqueness |
| ix_work_alumni | Own/public work-history loading and correlated alumni work lookup |
| ix_work_company_end_alumni | Company match and current-vs-previous employment lookup |
| ix_alumni_verification_year | Verified-only discovery, with graduation-year filtering and stable user ID |
| ix_user_skills_skill_user | Reverse skill-to-user matching; composite PK covers user-to-skill lookup |
| ix_alumni_guidance_area_user | Reverse guidance-area matching; composite PK covers own profile loading |

Primary keys and unique-name constraints create their normal database indexes as well. No indexes were added to every column. Role/domain/branch use case-insensitive substring matching; ordinary B-tree indexes would not accelerate arbitrary contains searches, so none were added for those text fields. Small catalog lookups are bounded and use substring search.

## APIs added

All routes require the existing cookie session. New browser writes validate Origin against the configured frontend origins; cross-site multipart writes are rejected.

| Method | Path | Authorization |
| --- | --- | --- |
| GET | /api/catalogs/{catalog}?q=&limit=20 | Authenticated |
| POST | /api/catalogs/{catalog} | ADMIN; JSON name |
| GET, POST | /api/profiles/alumni/me/work-experiences | ALUMNI |
| PUT, DELETE | /api/profiles/alumni/me/work-experiences/{id} | Owning ALUMNI |
| GET | /api/profiles/me/skills | STUDENT or ALUMNI |
| POST, DELETE | /api/profiles/me/skills/{skill_id} | Own STUDENT/ALUMNI relationship |
| GET | /api/profiles/alumni/me/guidance-areas | ALUMNI |
| POST, DELETE | /api/profiles/alumni/me/guidance-areas/{area_id} | Own ALUMNI relationship |
| GET | /api/profiles/alumni/me/verification | Own ALUMNI status; no filename or file |
| POST | /api/profiles/alumni/me/verification | ALUMNI multipart upload, field file |
| GET | /api/admin/verifications?page=1&page_size=20 | ADMIN pending submissions with proof |
| GET | /api/admin/verifications/{user_id} | ADMIN basic identity/submission information |
| GET | /api/admin/verifications/{user_id}/proof | ADMIN-only attachment download |
| POST | /api/admin/verifications/{user_id}/review | ADMIN; decision VERIFIED or REJECTED; reason required for rejection |
| GET | /api/alumni | STUDENT-only discovery |
| GET | /api/alumni/{user_id} | STUDENT-only verified professional profile |

Catalog values are companies, skills, and guidance-areas. Admin catalog creation is available through REST/API docs; no separate catalog-management screen is added. Lookup limit defaults to 20 and is capped at 50. Unknown references fail validation; duplicate skill/guidance relationships return 409.

Example work body:

```json
{
  "company_id": 1,
  "role": "Software Engineer",
  "domain": "Backend Engineering",
  "start_date": "2022-01-01",
  "end_date": null
}
```

Resolve company_id through the catalog endpoint; do not assume example ID 1 has a particular name.

## Verification lifecycle and file handling

1. A registered alumni uploads PNG, JPEG, or PDF proof, maximum 5 MiB. The request stream is bounded with a small allowance for multipart framing.
2. The backend inspects actual image/PDF structure. PDF files must be unencrypted, at most 20 pages, and must not contain catalog-level embedded files/scripts or open actions. Unsupported/corrupt files fail validation.
3. A random UUID filename is generated; the original filename is ignored. Files stay outside the public frontend and have no static route.
4. The profile becomes PENDING. The owner sees status and rejection notes, but cannot retrieve the file.
5. Administrators review the pending queue and download the proof through an authenticated route. Downloads use attachment disposition, no-store, nosniff, and a restrictive CSP.
6. Admin review changes only college identity status. Approval/rejection requires an existing pending proof; repeat decisions or approval without proof return 409.
7. Both decisions retire the file reference and delete the file. Decision metadata remains. Rejection requires an explanation; a new upload resets the request to PENDING. Verified users cannot replace proof.

Profile-row locks serialize upload/review transitions on PostgreSQL. Failed database writes clean up newly written files. Replaced and retired files are deleted after commit; an OS deletion failure logs a warning while the retired file is no longer retrievable by API. Downloaded admin copies remain the administrator's responsibility. This local structural validator is not a malware scanning service.

## Discovery and pagination

Only ACTIVE ALUMNI users with VERIFIED profiles are visible. The search and detail serializers include name, academic background, biography, availability, work, skills, and guidance areas. They omit email, password/hash, account internals, proof metadata, and document paths. Unverified details return 404.

Supported query parameters:

- company_id (stable catalog ID)
- role, domain, branch (case-insensitive literal substring)
- graduation_year, graduation_year_from, graduation_year_to
- skill_ids (repeat for multiple selections; maximum 20)
- guidance_area_ids (repeat; maximum 20)
- accepting_guidance_requests=true or false
- page (default 1), page_size (default 12; maximum 50)

All supplied filters combine with AND. Every selected skill/area must match. Company, role, and domain must match the same work-experience row. SQLAlchemy bound expressions and EXISTS subqueries prevent duplicate alumni rows and escape wildcard input; a separate count query produces totals.

When company_id is supplied, alumni currently at that company sort before previous employees. Within groups, order is case-insensitive name then unique user ID. Responses include company_relation CURRENT/PREVIOUS and all relevant work history for the UI. Without a company filter, sorting is name then ID.

Pagination uses LIMIT/OFFSET. Metadata includes page, page_size, total_results, and total_pages. Empty results have total_pages=0; a page beyond the end returns an empty list with valid totals. Profile associations are loaded in three batched queries per result page, avoiding one query per card.

## Frontend

- Alumni dashboard: multiple work histories with add/edit/delete, searchable company selection, skill and guidance management, proof submission/status, existing biography/background/availability editing.
- Student dashboard: shared skills management and a working Find alumni navigation card.
- find-alumni.html: authenticated filters, searchable native datalists, multi-select chips, actual professional cards, current/previous labels, clear empty/errors/loading states, bounded pagination.
- alumni-profile.html: verified profile visible to authenticated students, with full work history and no private identity data.
- admin.html: pending queue, authorized proof download, approve/reject decision and rejection reason.
- Existing landing, login, and registration copy now reflects live discovery; future interaction features remain explicitly upcoming.

Native labels, keyboard controls, focus outlines, live status regions, and responsive layouts continue the Phase 2.5 design. All scripts remain vanilla JavaScript. Catalog selections resolve a stable backend ID before submission. Uploads preserve credentials: "include" without overriding the browser's multipart boundary.

## Files created or changed

Created backend files:

- app/models/professional.py
- app/schemas/professional.py
- app/services/catalogs.py
- app/services/verification.py
- app/routes/professional.py
- app/routes/discovery.py
- app/routes/verification.py
- app/utils/upload_limit.py
- app/cli.py
- migrations/versions/002_professional_discovery.py
- tests/test_phase3.py

Changed backend files:

- app/models/__init__.py, app/models/profiles.py
- app/config.py, app/main.py
- requirements.txt, .gitignore
- tests/conftest.py (temporary isolated proof storage)

Created frontend files:

- find-alumni.html, alumni-profile.html, admin.html
- js/professional-ui.js, js/professional-profile.js
- js/find-alumni.js, js/alumni-profile.js, js/admin.js

Changed frontend files:

- alumni-dashboard.html, student-dashboard.html
- index.html, login.html, register.html
- css/style.css, js/api.js, js/dashboard.js

Documentation: README.md updated; PHASE3.md added. Ignored backend/.private files were used only for the local QA proof and read-only live smoke check.

## Verification results — 2026-09-02

- Alembic upgraded the actual local PostgreSQL database to 002_professional_discovery.
- All seven new tables and intended indexes were inspected. alembic check reported no new upgrade operations.
- Catalog seeding ran repeatedly without duplicate records or automatic user creation.
- FastAPI successfully reloaded Phase 3; /health reports database connected, and OpenAPI reports version 0.3.0.
- **47 automated tests passed:** the original 12 plus 35 Phase 3 cases, using in-memory SQLite and temporary proof directories.
- Tests cover role/ownership restrictions, multiple jobs, invalid dates/references, shared skills, duplicates, multiple guidance topics, approved-only discovery, same-job combined filters, company ordering, all-selected skills, stable multi-page pagination, page-size bounds, privacy, admin transitions, resubmission, supported image/PDF files, invalid/oversized uploads, and untrusted origins.
- Browser checks on local PostgreSQL: alumni login; two work experiences; Java/SQL skills; two guidance areas; proof upload; CLI-created admin login; authenticated proof download; approval; student login; student Python skill; discovery; combined filters; current Amazon/previous Microsoft labels; profile view; empty results and filter reset.
- Additional live API checks confirmed page-size bounds, end-of-results behavior, public profile field privacy, student proof access denied (403), missing public proof routes (404), and proof-reference retirement.
- New discovery/profile pages were checked at desktop and 390px/320px widths, with no horizontal overflow or unlabeled form controls. No major JavaScript console errors were observed.
- Actual multi-page ordering and unverified exclusion were tested in the safe automated fixtures; the local live database contained one verified QA alumni at the end of testing.

Existing Phase25 Student/Alumni QA accounts were reused. No fake alumni were seeded. A clearly labeled non-real-ID fixture was approved solely for local workflow testing. The temporary Phase3 QA admin is deactivated after verification; create your own administrator with the command above. Existing QA users and their professional test data remain available locally.

The native datalist appearance varies by browser. A full cross-browser/screen-reader audit and production upload storage/scanning are outside this phase. No Phase 4 work has started.
