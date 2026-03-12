# Project overview
- Flask 3 app serving dashboard pages (`/dashboard/*`) and auth flows; main entry `app.py`.
- Data: MySQL for users/roles; MongoDB for course/knowledge data; in-memory dict `users` for favorites (non-prod).
- Agents: `agents` (课程智能体) and `agents_kd` (知识库智能体) embedded via iframe; class KG pages under `/classkg/<course_id>`.
- Frontend: Jinja templates in `templates/`, assets under `static/`; layout base `layout.html`, dashboard pages in `templates/dashboard/`.
- Background: starts `mcp_server.py` subprocess; KG helpers in `KG/`; canvas/email utils in `utils/`.

## Non-negotiables
- Do not downgrade security: keep parameterized SQL via `with closing(get_conn())`; never store plaintext secrets in code (config currently holds keys).
- Preserve role checks: teachers can only access their courses (`teacher_courses`), sessions must gate `/dashboard/*`.
- Keep embed rules: student iframe URL = `student_url + username`; teacher access must respect course whitelist.
- Avoid destructive git actions; do not remove user-modified files; no network installs without approval.

## How to run & test
- Setup: Python 3.x; install from `requirement.txt`; ensure MySQL/Mongo reachable per `config.py` (`MYSQL_URL`, `MONGO_URL`), ports 7777/7778 as configured.
- Run: `python app.py` (starts Flask at `APP_PORT`, spawns MCP server).
- Test: no automated tests provided; sanity-check login/register, `/dashboard/agents`, `/dashboard/agent/<id>`, KG update endpoints.
- Lint/format: none enforced; keep consistent with existing style.

## Architecture boundaries
- routes: all in `app.py` (auth, dashboard pages, KG APIs, favorites, MCP chat).
- services/utils: `utils.canvas_utils`, `utils.email_verify`, `mcp_client`, `KG/*` for graph generation/loading.
- dao/db: `get_conn()` for MySQL; Mongo client initialized in `__main__`; avoid global cursors.
- templates/static: Jinja in `templates/`; dashboard pages `templates/dashboard/*.html`; assets in `static/`; KG HTML in `KG/course_graph_html`.

## Conventions
- Naming: course agents use IDs 1..10 with `name/description/student_url/teacher_url/image_url`; knowledge-base agents in `agents_kd`.
- Error handling: return JSON with HTTP codes for API endpoints; flash messages for auth flows; keep try/except with logging.
- Logging: use `print` currently; keep traceback on failures (MCP/KG generation).

## Change policy
- PR size: prefer small, reviewable diffs; isolate template vs backend changes.
- Required tests: manual verification of impacted routes/embeds; if touching DB, confirm read/write paths with sample data.
- Docs/migrations: update `AGENTS.md` when adding agents or changing embed rules; document new env/config switches.
