# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Flask website + lightweight customer management system for a single gym (D-Lion Gym): a public marketing site, one login page shared by staff and members, a member self-service dashboard, and an admin area for staff to manage member records. Data lives in Supabase (Postgres); the app is deployed on Vercel.

## Commands

Setup:
```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Required environment variables (get from Supabase → Project Settings → API Keys):
```bash
export SUPABASE_URL=https://<project-ref>.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=<service_role secret key>
export SECRET_KEY=<random string, for Flask session signing>
```

Run the dev server:
```bash
python app.py
```

Flask CLI commands (`db.py` registers these):
```bash
flask --app app seed-db                                          # demo admin + demo members
flask --app app create-admin "Full Name" email@x.com "password"  # create/reset a staff login
```

There is no test suite and no linter configured in this repo.

## Architecture

**Two separate login paths, one session model.** This is the thing to understand before touching auth or `g.user`:

- **Staff/admin** accounts live in the `users` table with a `password_hash` (werkzeug). They log in with a real password.
- **Members** have *no* `users` row at all. They authenticate straight against the `members` table: email must match, and the submitted password must match `members.phone` (digits-only comparison via `_digits()` in `app.py`). This means staff adding someone through `/admin/members/new` *is* the signup step — no separate account provisioning happens.
- `session["role"]` is `"admin"` or `"member"`; `session["identity_id"]` is the `users.id` or `members.id` accordingly. `load_logged_in_user` (in `register_routes`) resolves this each request into `g.user` (a dict with `id`/`full_name`/`email`/`role`, synthesized for members) and, for members only, also sets `g.member` to the full row so `member_dashboard` doesn't need a second query. Templates check `g.user['role'] == 'admin'` to branch UI.

**Database access goes through the Supabase REST client, not raw SQL/psycopg2.** `db.py`'s `get_db()` returns a `supabase.Client` authenticated with the **service_role key**, which bypasses Row Level Security — RLS is enabled on both `users` and `members` specifically so nothing but this backend (holding that key) can read/write them via Supabase's public API. Query style is the `.table("x").select().eq()...execute()` builder, not SQL strings. `execute().data` is a list of dicts; `execute().count` is used for `count="exact"` queries (see `admin_dashboard`).

**Schema is managed in Supabase directly, not by the app.** There's no `init_db`/migration code in this repo — the `users`/`members` tables and RLS policies were created via Supabase migrations outside this codebase. `db.py` only seeds/queries; it doesn't define schema.

**Unique-constraint handling**: `db_module.APIError` (re-exported from `postgrest.exceptions`) and `db_module.is_unique_violation(err)` (checks Postgres code `23505`) are used in `app.py`'s member create/edit routes to turn a duplicate-email insert into a flashed error instead of a 500.

**Deployment**: Vercel project `d-lion-gym`, framework preset `flask` (Vercel auto-detects the `app` variable at module level in `app.py` — no `vercel.json` needed). Auto-deploy from git push is **not** wired up (Vercel's GitHub App isn't linked to the account); deployments are pushed directly via the Vercel API/dashboard with the full file set each time. Env vars (`SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) are set on the Vercel project, not committed anywhere.

## Request flow for the admin/member CRUD pages

`app.py` is a single file using the app-factory pattern (`create_app()` → `register_routes(app)`) rather than blueprints — everything is one `register_routes` closure. Form parsing/validation for members is centralized in the two module-level helpers `_member_form_data()` and `_validate_member()` at the bottom of `app.py`, shared by both the add and edit routes. Phone is a required field specifically because it doubles as the member's login password.
