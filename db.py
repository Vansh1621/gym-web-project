"""
Database helpers for D Lion Gym.

Uses plain sqlite3 (no ORM) so the code stays easy to read for anyone
who already knows SQL. The database file lives in instance/dlion.sqlite3
and is created automatically the first time the app runs.
"""
import sqlite3
from datetime import date, timedelta
import click
from flask import current_app, g
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


SCHEMA = """
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS members;

CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'member')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE members (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name    TEXT NOT NULL,
    email        TEXT UNIQUE NOT NULL,
    phone        TEXT,
    plan         TEXT NOT NULL DEFAULT 'Basic',
    join_date    TEXT NOT NULL,
    expiry_date  TEXT,
    status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'frozen')),
    notes        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()


def seed_db():
    """Insert a demo admin, a demo member login, and a handful of member records."""
    db = get_db()
    today = date.today()

    db.execute(
        "INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("Gym Admin", "admin@dlion.gym", generate_password_hash("admin123"), "admin"),
    )
    db.execute(
        "INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("Rahul Mehta", "rahul@example.com", generate_password_hash("member123"), "member"),
    )

    demo_members = [
        ("Rahul Mehta", "rahul@example.com", "9876500001", "Gold", today - timedelta(days=40), today + timedelta(days=320), "active", "Prefers evening slot"),
        ("Ananya Sharma", "ananya@example.com", "9876500002", "Basic", today - timedelta(days=120), today + timedelta(days=245), "active", ""),
        ("Vikram Singh", "vikram@example.com", "9876500003", "Platinum", today - timedelta(days=10), today + timedelta(days=355), "active", "Personal training add-on"),
        ("Priya Verma", "priya@example.com", "9876500004", "Basic", today - timedelta(days=400), today - timedelta(days=35), "inactive", "Plan expired"),
        ("Karan Malhotra", "karan@example.com", "9876500005", "Gold", today - timedelta(days=200), today + timedelta(days=165), "frozen", "Travelling, freeze requested"),
    ]
    db.executemany(
        """INSERT INTO members (full_name, email, phone, plan, join_date, expiry_date, status, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        demo_members,
    )
    db.commit()


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Create fresh tables (wipes existing data)."""
    init_db()
    click.echo("Initialized the database.")


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
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        db.execute(
            "UPDATE users SET full_name=?, password_hash=?, role='admin' WHERE email=?",
            (full_name, generate_password_hash(password), email),
        )
        click.echo(f"Updated existing account for {email} to admin with the new password.")
    else:
        db.execute(
            "INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
            (full_name, email, generate_password_hash(password)),
        )
        click.echo(f"Created admin account for {email}.")
    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_db_command)
    app.cli.add_command(create_admin_command)
