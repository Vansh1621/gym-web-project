# D-Lion Gym — Website + Customer Management System

A minimal gym website built with Flask + Supabase (Postgres): a public
marketing site, a login page, a member self-service dashboard, and an admin
area for staff to manage member records (add / edit / search / delete).
Deployed on Vercel.

Live site: https://d-lion-gym.vercel.app

## What's included

- **Public site**: Home, About, Programs, Trainers, Pricing, Contact
- **Login**: staff use a real password (set via `create-admin`); members log in with their email and the phone number staff put on file for them -- no separate account needs creating when a member is added
- **Member dashboard**: a logged-in member sees their own plan, status, and renewal date
- **Admin dashboard** (`/admin`): member counts by status, recently added members
- **Member management** (`/admin/members`): search/filter, add, edit, delete member records

## Requirements

- Python 3.10+
- A Supabase project (free tier is fine) — provides the Postgres database

## Setup

```bash
cd dlion-gym
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Set these environment variables (get them from Supabase → Project Settings → API Keys):

```bash
export SUPABASE_URL=https://<your-project-ref>.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=<your service_role secret key>
export SECRET_KEY=<a long random string>
```

## Run it

```bash
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

The database schema (`users`, `members` tables, with Row Level Security
enabled so only this backend's service_role key can read/write them) is
managed directly in Supabase rather than by the app. Seed demo data with:

```bash
flask --app app seed-db     # adds demo accounts + members
```

### Demo logins

| Role   | Email                 | Password              |
|--------|------------------------|-----------------------|
| Staff  | admin@dlion.gym        | admin123              |
| Member | rahul@example.com      | 9876500001 (their phone) |

**Change the admin password (and the `SECRET_KEY`) before using this for a real gym.**

Create/reset a real staff login with:

```bash
flask --app app create-admin "Owner Name" owner@realemail.com "a-strong-password"
```

## Project structure

```
app.py                 Flask app + routes
db.py                  Database helpers (Supabase client, seed data, CLI commands)
templates/             Jinja2 HTML templates
  admin/               Staff dashboard, member list, add/edit form
  member/              Member's own dashboard
static/css/style.css   All styling (single stylesheet, minimal dark + gold theme)
static/js/main.js      Mobile nav toggle
```

## Deployment

Live on **Vercel** (project `gym-web-project`), deployed directly from this
repo's code. Data lives in **Supabase** Postgres.

Auto-deploy on `git push` isn't wired up yet — Vercel's GitHub App needs to
be linked to this account first (Vercel dashboard → Settings → Git → Connect
GitHub). Once that's done, connect the repo in the Vercel dashboard
(Project → Settings → Git) and every push to `main` will deploy automatically.
Until then, redeploy from the Vercel dashboard or CLI after pushing changes.

Environment variables set on Vercel (Project Settings → Environment Variables):

- `SECRET_KEY` — random string for Flask session signing
- `SUPABASE_URL` — this project's Supabase API URL
- `SUPABASE_SERVICE_ROLE_KEY` — service_role secret key (server-side only, bypasses RLS)

The contact form on `/contact` doesn't send an email yet (wire it to a
service like Resend or SMTP, or write submissions to the database so staff
can see requests in the admin panel), and new members/payments are added by
staff through `/admin/members/new` rather than online sign-up. Both are
reasonable follow-on features.
