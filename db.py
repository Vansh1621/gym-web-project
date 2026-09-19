"""
Database helpers for D Lion Gym.

Talks to Postgres through the Supabase REST API (via the `supabase` Python
client) instead of a local file, so the app works on serverless hosts like
Vercel that don't have persistent disk. The client authenticates with the
service_role key, which bypasses Row Level Security -- RLS is enabled on
both tables specifically so nothing but this backend can read or write them.
"""
from datetime import date, timedelta

import click
from flask import current_app, g
from flask.cli import with_appcontext
from postgrest.exceptions import APIError
from supabase import create_client
from werkzeug.security import generate_password_hash

UNIQUE_VIOLATION = "23505"


def get_db():
    if "db" not in g:
        g.db = create_client(
            current_app.config["SUPABASE_URL"],
            current_app.config["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return g.db


def close_db(e=None):
    g.pop("db", None)


def is_unique_violation(err):
    return isinstance(err, APIError) and getattr(err, "code", None) == UNIQUE_VIOLATION


def seed_db():
    """Insert a demo admin, a demo member login, and a handful of member records."""
    db = get_db()
    today = date.today()

    db.table("users").insert([
        {
            "full_name": "Gym Admin",
            "email": "admin@dlion.gym",
            "password_hash": generate_password_hash("admin123"),
            "role": "admin",
        },
        {
            "full_name": "Rahul Mehta",
            "email": "rahul@example.com",
            "password_hash": generate_password_hash("member123"),
            "role": "member",
        },
    ]).execute()

    demo_members = [
        ("Rahul Mehta", "rahul@example.com", "9876500001", "Gold", today - timedelta(days=40), today + timedelta(days=320), "active", "Prefers evening slot"),
        ("Ananya Sharma", "ananya@example.com", "9876500002", "Basic", today - timedelta(days=120), today + timedelta(days=245), "active", ""),
        ("Vikram Singh", "vikram@example.com", "9876500003", "Platinum", today - timedelta(days=10), today + timedelta(days=355), "active", "Personal training add-on"),
        ("Priya Verma", "priya@example.com", "9876500004", "Basic", today - timedelta(days=400), today - timedelta(days=35), "inactive", "Plan expired"),
        ("Karan Malhotra", "karan@example.com", "9876500005", "Gold", today - timedelta(days=200), today + timedelta(days=165), "frozen", "Travelling, freeze requested"),
    ]
    db.table("members").insert([
        {
            "full_name": full_name, "email": email, "phone": phone, "plan": plan,
            "join_date": str(join_date), "expiry_date": str(expiry_date),
            "status": status, "notes": notes,
        }
        for full_name, email, phone, plan, join_date, expiry_date, status, notes in demo_members
    ]).execute()


@click.command("seed-db")
@with_appcontext
def seed_db_command():
    """Add demo admin/member accounts and sample member records."""
    seed_db()
    click.echo("Seeded demo data. Admin login: admin@dlion.gym / admin123")


@click.command("create-admin")
@click.argument("full_name")
@click.argument("email")
@click.argument("password")
@with_appcontext
def create_admin_command(full_name, email, password):
    """Create (or reset) a staff login: flask --app app create-admin "Name" email pass"""
    db = get_db()
    existing = db.table("users").select("id").eq("email", email).execute()
    if existing.data:
        db.table("users").update({
            "full_name": full_name,
            "password_hash": generate_password_hash(password),
            "role": "admin",
        }).eq("email", email).execute()
        click.echo(f"Updated existing account for {email} to admin with the new password.")
    else:
        db.table("users").insert({
            "full_name": full_name,
            "email": email,
            "password_hash": generate_password_hash(password),
            "role": "admin",
        }).execute()
        click.echo(f"Created admin account for {email}.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(seed_db_command)
    app.cli.add_command(create_admin_command)
