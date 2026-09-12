# Final pre-deployment UX and requirement pass

The architecture, session authentication, REST message persistence, WebSocket delivery, and existing database models remain unchanged.

## Changes

- Login and registration have an eye icon plus Show/Hide button. The shared `frontend/js/ui.js` helper updates input type, accessible label, and aria-pressed; native keyboard behavior, labels, required/minlength validation and autocomplete remain intact.
- Admin catalog management supports search, 20-item browsing pages, and additions for Companies, Skills and Guidance Areas. Submission disables the button, user content is rendered as text, and duplicates return a clear 409 message. No delete action was added.
- The catalog GET API accepts an optional non-negative `offset` (default 0). Existing clients and response shapes are unchanged. POST remains admin-only, protected by session authentication and CSRF. Database uniqueness remains the final duplicate protection.
- Default skill and guidance-area catalogs cover software, cloud, data, core engineering and career development. Repeat seeding preserves existing IDs/custom entries and creates no users. Catalog labels naming technologies do not install any framework or dependency.

## Administrator access

From `backend`, with the existing virtual environment active:

```powershell
python -m app.cli create-admin --name "College Administrator" --email administrator@example.edu
```

The CLI prompts privately for the password and confirmation. Admin cannot publicly register. Use normal `login.html`; the role-based redirect opens `admin.html`, containing the verification queue and Catalog management section.

To update existing catalogs safely:

```powershell
python -m app.cli seed-catalogs
```

This command was run twice successfully against the local development database. No real secret values were modified.

## Distribution boundaries

`.gitignore` excludes `.env`, `.env.docker`, `.private` QA artifacts, private uploads and local DB/SQLite files. `.gitattributes` additionally excludes those paths from source archives. Docker contexts exclude local environment/database artifacts and Dockerfiles copy explicit application/static paths only. Example environment files contain placeholders and remain distributable.

This workspace has no Git repository metadata, so current tracked-file status cannot be audited. The ignore rules are supplied for repository use; do not distribute an unfiltered copy of the whole local working directory. Keep actual env files and database/proof volumes outside release source. Browser QA used an isolated temporary SQLite preview and did not alter real accounts.

The supplied ignore and export-ignore rules were verified with Git in a separate temporary repository for real-env paths, proof uploads, QA files, and local databases; all sample private paths were excluded.

## Regression results

- Standard suite: **134 passed, 9 skipped** (PostgreSQL-specific tests run separately).
- PostgreSQL integrity/concurrency suite: **9 passed**.
- Frontend real-time suite: **4 passed**.
- Total: **147 passing tests**.
- Alembic check: no new upgrade operations; no migration needed.
- Dependency check and modified JavaScript syntax checks: passed.
- Browser: admin login/redirect, company/skill/guidance additions, case-insensitive duplicate feedback, search, keyboard password toggles and a 390px mobile check passed; no browser console errors.

The complete suites cover registration, login, alumni/admin verification, discovery, guidance requests, connections, REST messaging, WebSockets and CSRF. Added catalog tests cover both STUDENT and ALUMNI receiving 403 for all three creation APIs, admin creation/search, duplicate prevention, offset pagination, and repeatable seeds without user creation.

Commands from `backend`:

```powershell
python -m pytest -q
python scripts/test_postgres.py
python -m alembic check
python -m pip check
```

From project root:

```powershell
node --test frontend/tests/realtime.test.cjs
```

## Files

Frontend: `login.html`, `register.html`, `admin.html`, `js/ui.js`, `js/admin.js`, `css/style.css`, `.dockerignore`.

Backend: `app/routes/professional.py`, `app/services/catalogs.py`, `tests/test_phase3.py`, `.gitignore`, `.dockerignore`.

Root: `.gitignore`, `.gitattributes`, `README.md`, `PHASE6.md`, `PREDEPLOYMENT_UX.md`.
