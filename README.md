# D Lion Gym — Website + Customer Management System

A minimal gym website built with Flask + SQLite: a public marketing site, a
login page, a member self-service dashboard, and an admin area for staff to
manage member records (add / edit / search / delete).

## What's included

- **Public site**: Home, About, Programs, Trainers, Pricing, Contact
- **Login**: one login page for both members and staff (role decided by the account)
- **Member dashboard**: a logged-in member sees their own plan, status, and renewal date
- **Admin dashboard** (`/admin`): member counts by status, recently added members
- **Member management** (`/admin/members`): search/filter, add, edit, delete member records

## Requirements

- Python 3.10+

## Setup

```bash
cd dlion-gym
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run it

```bash
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

The SQLite database (`instance/dlion.sqlite3`) is created automatically the
first time you run the app, and seeded with demo data so you can try
everything immediately.

### Demo logins

| Role   | Email                 | Password  |
|--------|------------------------|-----------|
| Staff  | admin@dlion.gym        | admin123  |
| Member | rahul@example.com      | member123 |

**Change the admin password (and the `SECRET_KEY`) before using this for a real gym.**

### Resetting the database

If you want to wipe and reseed the data:

```bash
rm instance/dlion.sqlite3
python app.py     # recreates + reseeds automatically
```

Or, using Flask's CLI:

```bash
flask --app app init-db     # wipes and recreates tables
flask --app app seed-db     # adds demo accounts + members
```

## Project structure

```
app.py                 Flask app + routes
db.py                  Database helpers (schema, seed data)
templates/             Jinja2 HTML templates
  admin/               Staff dashboard, member list, add/edit form
  member/              Member's own dashboard
static/css/style.css   All styling (single stylesheet, minimal dark + gold theme)
static/js/main.js      Mobile nav toggle
instance/              SQLite database lives here (created automatically)
```

## Deploying it for real (with a database that survives redeploys)

The app already ships with `gunicorn` (a production server) and a `Procfile`,
so it's ready for a host that runs Python apps from a Git repo — Render or
Railway are the simplest for a project this size. Either one gives you HTTPS
and a custom domain for free once you're on a paid instance.

**1. Put the code in a private GitHub repo.** Both hosts deploy by connecting
to a repo and redeploying on every push.

**2. Create the web service.**
- Render: New → Web Service → connect the repo → build command
  `pip install -r requirements.txt`, start command `gunicorn app:app`.
- Railway: New Project → Deploy from GitHub repo — it detects the `Procfile`
  automatically.
- Pick a paid instance (Render's starter is ~$7/month, Railway is usage-based
  at roughly the same). The free tiers on both exist, but they spin the app
  down when idle, which means slow first loads for members — not something
  you want on a gym's live site.

**3. Make the database persistent.** This is the part that's easy to miss:
by default, anything your app writes to disk (the SQLite file) is wiped on
every redeploy, because the container is rebuilt from scratch.
- On Render: add a **persistent disk** (from $0.25/GB/month — 1GB is plenty
  for a single gym's member list), mount it at e.g. `/var/data`, and set the
  environment variable `DATABASE_PATH=/var/data/dlion.sqlite3`. The app reads
  that variable automatically (see `app.py`).
- On Railway: attach a **volume** the same way, or add their managed
  Postgres add-on if you'd rather not think about disks at all (see below).
- Either way, set up a simple backup: most hosts let you open a one-off shell
  on the running service — periodically run something like
  `cp /var/data/dlion.sqlite3 backup-$(date +%F).sqlite3` and download it, or
  push it to cloud storage. For a single small gym, SQLite is genuinely fine —
  it's the "forgetting to persist the file" that causes data loss, not SQLite
  itself.
- If the gym grows into multiple locations or you want a "proper" managed
  database instead of a disk, swap in Render's or Railway's managed
  PostgreSQL later (a few hours of work to change the queries in `db.py`
  from `sqlite3` to `psycopg2`/SQLAlchemy) — not necessary to launch.

**4. Set real secrets and lock down the seeded accounts.**
```bash
# set an environment variable on the host (don't hardcode it in code)
SECRET_KEY=<a long random string>

# then, once deployed, open a shell on the host and run:
flask --app app create-admin "Owner Name" owner@realemail.com "a-strong-password"
```
That updates (or creates) a real staff login with a real password, so you're
not leaving `admin123` live on the internet. Delete or repurpose the seeded
demo member the same way once real members are added.

**5. Point a real domain at it.** Buy a domain (₹700–1,200/year for a
`.com`/`.in` from Namecheap, GoDaddy, or a local registrar), add it in the
host's dashboard, and update the domain's DNS records as they instruct.
SSL (the padlock/https) is issued automatically by both hosts — no extra cost.

**6. Two things that are still manual, on purpose:** the contact form on
`/contact` doesn't send an email yet (wire it to a service like Resend or
SMTP, or just have it write to the database so staff can see requests in the
admin panel), and new members/payments are added by staff through
`/admin/members/new` rather than online sign-up. Both are reasonable
follow-on features once the core site is live and being used.
