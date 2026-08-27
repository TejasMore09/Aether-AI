# Restoring on a fresh machine

Written for the case where this laptop gets formatted. Everything needed is
on GitHub; this is the shortest path from a blank Windows install back to a
running system.

**Clone from GitHub, not from the Google Drive copy.** Drive syncs the live
`.git` directory while git is writing to it, so the synced copy can be subtly
corrupt in ways that only surface later. The Drive folder is a safety net for
the handful of files git deliberately excludes — nothing more.

---

## Before handing the laptop over

1. **Push everything.**

   ```bash
   git status
   git push
   ```

   `git status` should show nothing but ignored files. Anything uncommitted
   does not exist as far as recovery is concerned.

2. **Save the secrets.** These are the only things here that GitHub does not
   have, and a format destroys all of them.

   **The root `.env` file.** It is gitignored, so it exists nowhere else. It
   currently holds:

   - `OPENAI_API_KEY`, `OPENAI_BASE_URL`
   - `GEMINI_API_KEY`
   - `GMAIL_SENDER`, `GMAIL_APP_PASSWORD`, `ALERT_RECIPIENT`

   Copy the whole file into a password manager as a secure note.

   **Two Windows user environment variables**, which live outside any file:

   - `GEMINI_API_KEY`
   - `API_KEY_21ST`

   ```powershell
   [Environment]::GetEnvironmentVariable('GEMINI_API_KEY','User')
   [Environment]::GetEnvironmentVariable('API_KEY_21ST','User')
   ```

   A password manager, not the repo. `.gitignore` will not save you from a
   `git add -f`, and a key committed once is in the history for good.

   `GMAIL_APP_PASSWORD` is worth rotating rather than restoring — app
   passwords are cheap to reissue and you cannot be sure where a formatted
   disk ends up.

3. **Anything else you care about?** The Postgres data is test tenants and is
   not worth preserving. If you want it anyway:

   ```bash
   docker exec aether-db pg_dump -U aether aether > aether-backup.sql
   ```

---

## On the new machine

Install first: [Docker Desktop](https://docker.com/products/docker-desktop),
[Python 3.12](https://python.org/downloads), [Node 24](https://nodejs.org),
[git](https://git-scm.com), and the
[Claude Code CLI](https://claude.com/claude-code).

### 1. Clone

```bash
git clone https://github.com/TejasMore09/Aether-AI.git
cd Aether-AI
```

### 2. Python and infrastructure

```powershell
cd platform
py -3.12 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
```

Start Docker Desktop, then:

```powershell
docker compose up -d
```

### 3. Configuration

```powershell
copy .env.example .env
```

Then edit `platform\.env` and set real values for:

- `AETHER_JWT_SECRET`
- `AETHER_STAFF_JWT_SECRET` — must differ from the one above; sharing them
  collapses the separation between customer and staff identity

Generate each with:

```powershell
.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 4. Database schema

```powershell
$env:AETHER_MIGRATION_DATABASE_URL="postgresql+psycopg://aether:aether_dev_only@localhost:5433/aether"
.venv\Scripts\alembic upgrade head
```

### 5. Confirm it works

```powershell
.venv\Scripts\pytest -q
```

160 tests should pass. If the Postgres-marked ones skip, the database is not
up — check `docker compose ps`.

### 6. Front ends

```powershell
cd web; npm install; copy .env.example .env.local
cd ..\console; npm install; copy .env.example .env.local
```

### 7. Environment variables

```powershell
setx GEMINI_API_KEY "<from your password manager>"
setx API_KEY_21ST "<from your password manager>"
```

Restart the terminal — and Claude Code — afterwards. `setx` only affects
processes started after it runs, which is easy to miss because the command
reports success either way.

### 8. First platform admin

The staff console needs one, and the bootstrap command refuses to run once any
admin exists:

```powershell
.venv\Scripts\python -m aether.main_brain.bootstrap you@company.com --role admin
```

---

## Running everything

Each in its own shell, from `platform/`:

```powershell
.venv\Scripts\uvicorn aether.control_plane.app:app --port 8100 --reload
```

```powershell
.venv\Scripts\uvicorn aether.agent_runtime.app:app --port 8200 --reload
```

```powershell
.venv\Scripts\uvicorn aether.main_brain.app:app --port 8300 --reload
```

```powershell
cd web; npm run dev        # customer dashboard, port 3000
```

```powershell
cd console; npm run dev    # staff console, port 3100
```

The monitor worker needs Temporal from `docker compose`:

```powershell
.venv\Scripts\python -m aether.worker
```

---

## A note on where the repo lives

Git and file-sync tools corrupt each other — both write to the same files
without coordinating, and `.git` is the part that suffers. If you keep using
Drive, treat GitHub as the authoritative copy and Drive as convenience only.

The cleaner arrangement is to keep the working repository outside the synced
folder and rely on `git push` for durability, which is what it is for.
