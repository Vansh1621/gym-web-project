import os
from datetime import date, datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import check_password_hash, generate_password_hash

import db as db_module


def create_app():
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
        # DATABASE_PATH lets you point at a persistent disk mount in production
        # (e.g. Render/Railway persistent volumes) instead of the app folder,
        # which is wiped on every redeploy.
        DATABASE=os.environ.get("DATABASE_PATH", os.path.join(app.instance_path, "dlion.sqlite3")),
    )
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(os.path.dirname(app.config["DATABASE"]) or ".", exist_ok=True)
    db_module.init_app(app)

    # Auto-create + seed the database on first run so the app works out of the box.
    if not os.path.exists(app.config["DATABASE"]):
        with app.app_context():
            db_module.init_db()
            db_module.seed_db()

    register_routes(app)
    return app


# ---------- auth helpers ----------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login", next=request.path))
        if g.user["role"] != "admin":
            flash("That page is only available to gym staff.", "error")
            return redirect(url_for("member_dashboard"))
        return view(*args, **kwargs)
    return wrapped


def register_routes(app):

    @app.before_request
    def load_logged_in_user():
        user_id = session.get("user_id")
        if user_id is None:
            g.user = None
        else:
            db = db_module.get_db()
            g.user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    @app.context_processor
    def inject_globals():
        return {"current_year": datetime.now().year}

    # ---------- public marketing site ----------

    @app.route("/")
    def home():
        return render_template("index.html")

    @app.route("/about")
    def about():
        return render_template("about.html")

    @app.route("/programs")
    def programs():
        return render_template("programs.html")

    @app.route("/trainers")
    def trainers():
        return render_template("trainers.html")

    @app.route("/pricing")
    def pricing():
        return render_template("pricing.html")

    @app.route("/contact")
    def contact():
        return render_template("contact.html")

    # ---------- auth ----------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            db = db_module.get_db()
            user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

            error = None
            if user is None or not check_password_hash(user["password_hash"], password):
                error = "Incorrect email or password."

            if error is None:
                session.clear()
                session["user_id"] = user["id"]
                flash(f"Welcome back, {user['full_name'].split(' ')[0]}!", "success")
                if user["role"] == "admin":
                    return redirect(url_for("admin_dashboard"))
                return redirect(url_for("member_dashboard"))
            flash(error, "error")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You've been logged out.", "success")
        return redirect(url_for("home"))

    # ---------- member area ----------

    @app.route("/member/dashboard")
    @login_required
    def member_dashboard():
        db = db_module.get_db()
        member = db.execute("SELECT * FROM members WHERE email = ?", (g.user["email"],)).fetchone()
        days_left = None
        if member and member["expiry_date"]:
            try:
                exp = datetime.strptime(member["expiry_date"], "%Y-%m-%d").date()
                days_left = (exp - date.today()).days
            except ValueError:
                days_left = None
        return render_template("member/dashboard.html", member=member, days_left=days_left)

    # ---------- admin: customer management system ----------

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        db = db_module.get_db()
        total = db.execute("SELECT COUNT(*) c FROM members").fetchone()["c"]
        active = db.execute("SELECT COUNT(*) c FROM members WHERE status='active'").fetchone()["c"]
        inactive = db.execute("SELECT COUNT(*) c FROM members WHERE status='inactive'").fetchone()["c"]
        frozen = db.execute("SELECT COUNT(*) c FROM members WHERE status='frozen'").fetchone()["c"]
        recent = db.execute(
            "SELECT * FROM members ORDER BY created_at DESC LIMIT 5"
        ).fetchall()
        return render_template(
            "admin/dashboard.html",
            total=total, active=active, inactive=inactive, frozen=frozen, recent=recent,
        )

    @app.route("/admin/members")
    @admin_required
    def admin_members():
        db = db_module.get_db()
        q = request.args.get("q", "").strip()
        status = request.args.get("status", "")
        plan = request.args.get("plan", "")

        sql = "SELECT * FROM members WHERE 1=1"
        params = []
        if q:
            sql += " AND (full_name LIKE ? OR email LIKE ? OR phone LIKE ?)"
            like = f"%{q}%"
            params += [like, like, like]
        if status:
            sql += " AND status = ?"
            params.append(status)
        if plan:
            sql += " AND plan = ?"
            params.append(plan)
        sql += " ORDER BY full_name ASC"

        members = db.execute(sql, params).fetchall()
        return render_template(
            "admin/members.html", members=members, q=q, status=status, plan=plan
        )

    @app.route("/admin/members/new", methods=["GET", "POST"])
    @admin_required
    def admin_member_new():
        if request.method == "POST":
            data = _member_form_data()
            error = _validate_member(data)
            if error:
                flash(error, "error")
                return render_template("admin/member_form.html", member=data, mode="new")
            db = db_module.get_db()
            try:
                db.execute(
                    """INSERT INTO members (full_name, email, phone, plan, join_date, expiry_date, status, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (data["full_name"], data["email"], data["phone"], data["plan"],
                     data["join_date"], data["expiry_date"], data["status"], data["notes"]),
                )
                db.commit()
            except db_module.sqlite3.IntegrityError:
                flash("A member with that email already exists.", "error")
                return render_template("admin/member_form.html", member=data, mode="new")
            flash(f"Added {data['full_name']} to the member list.", "success")
            return redirect(url_for("admin_members"))
        return render_template("admin/member_form.html", member=None, mode="new")

    @app.route("/admin/members/<int:member_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_member_edit(member_id):
        db = db_module.get_db()
        existing = db.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
        if existing is None:
            flash("Member not found.", "error")
            return redirect(url_for("admin_members"))

        if request.method == "POST":
            data = _member_form_data()
            error = _validate_member(data)
            if error:
                flash(error, "error")
                return render_template("admin/member_form.html", member=data, mode="edit", member_id=member_id)
            try:
                db.execute(
                    """UPDATE members SET full_name=?, email=?, phone=?, plan=?, join_date=?,
                       expiry_date=?, status=?, notes=? WHERE id=?""",
                    (data["full_name"], data["email"], data["phone"], data["plan"],
                     data["join_date"], data["expiry_date"], data["status"], data["notes"], member_id),
                )
                db.commit()
            except db_module.sqlite3.IntegrityError:
                flash("A member with that email already exists.", "error")
                return render_template("admin/member_form.html", member=data, mode="edit", member_id=member_id)
            flash(f"Updated {data['full_name']}.", "success")
            return redirect(url_for("admin_members"))

        return render_template("admin/member_form.html", member=existing, mode="edit", member_id=member_id)

    @app.route("/admin/members/<int:member_id>/delete", methods=["POST"])
    @admin_required
    def admin_member_delete(member_id):
        db = db_module.get_db()
        member = db.execute("SELECT full_name FROM members WHERE id = ?", (member_id,)).fetchone()
        db.execute("DELETE FROM members WHERE id = ?", (member_id,))
        db.commit()
        if member:
            flash(f"Removed {member['full_name']} from the member list.", "success")
        return redirect(url_for("admin_members"))


def _member_form_data():
    return {
        "full_name": request.form.get("full_name", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "phone": request.form.get("phone", "").strip(),
        "plan": request.form.get("plan", "Basic"),
        "join_date": request.form.get("join_date", ""),
        "expiry_date": request.form.get("expiry_date", "") or None,
        "status": request.form.get("status", "active"),
        "notes": request.form.get("notes", "").strip(),
    }


def _validate_member(data):
    if not data["full_name"]:
        return "Full name is required."
    if not data["email"] or "@" not in data["email"]:
        return "A valid email is required."
    if not data["join_date"]:
        return "Join date is required."
    return None


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
