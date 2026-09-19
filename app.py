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
        SUPABASE_URL=os.environ.get("SUPABASE_URL"),
        SUPABASE_SERVICE_ROLE_KEY=os.environ.get("SUPABASE_SERVICE_ROLE_KEY"),
    )
    db_module.init_app(app)
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
        role = session.get("role")
        identity_id = session.get("identity_id")
        g.user = None
        g.member = None
        if identity_id is None:
            return
        db = db_module.get_db()
        if role == "admin":
            res = db.table("users").select("*").eq("id", identity_id).execute()
            g.user = res.data[0] if res.data else None
        elif role == "member":
            res = db.table("members").select("*").eq("id", identity_id).execute()
            member = res.data[0] if res.data else None
            if member:
                g.member = member
                g.user = {
                    "id": member["id"],
                    "full_name": member["full_name"],
                    "email": member["email"],
                    "role": "member",
                }

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
            password = request.form.get("password", "").strip()
            db = db_module.get_db()

            # Staff log in with a real password set by an admin.
            staff_res = db.table("users").select("*").eq("email", email).execute()
            staff = staff_res.data[0] if staff_res.data else None
            if staff and check_password_hash(staff["password_hash"], password):
                session.clear()
                session["role"] = "admin"
                session["identity_id"] = staff["id"]
                flash(f"Welcome back, {staff['full_name'].split(' ')[0]}!", "success")
                return redirect(url_for("admin_dashboard"))

            # Members log in with the phone number staff put on file for them --
            # no separate account needs to be created when a member is added.
            member_res = db.table("members").select("*").eq("email", email).execute()
            member = member_res.data[0] if member_res.data else None
            if member and password and member.get("phone") and _digits(password) == _digits(member["phone"]):
                session.clear()
                session["role"] = "member"
                session["identity_id"] = member["id"]
                flash(f"Welcome back, {member['full_name'].split(' ')[0]}!", "success")
                return redirect(url_for("member_dashboard"))

            flash("Incorrect email or password.", "error")
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
        member = g.member
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
        total = db.table("members").select("id", count="exact").execute().count
        active = db.table("members").select("id", count="exact").eq("status", "active").execute().count
        inactive = db.table("members").select("id", count="exact").eq("status", "inactive").execute().count
        frozen = db.table("members").select("id", count="exact").eq("status", "frozen").execute().count
        recent = (
            db.table("members").select("*").order("created_at", desc=True).limit(5).execute().data
        )
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

        query = db.table("members").select("*")
        if status:
            query = query.eq("status", status)
        if plan:
            query = query.eq("plan", plan)
        members = query.order("full_name").execute().data

        if q:
            ql = q.lower()
            members = [
                m for m in members
                if ql in (m["full_name"] or "").lower()
                or ql in (m["email"] or "").lower()
                or ql in (m.get("phone") or "").lower()
            ]
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
                db.table("members").insert(data).execute()
            except db_module.APIError as e:
                if not db_module.is_unique_violation(e):
                    raise
                flash("A member with that email already exists.", "error")
                return render_template("admin/member_form.html", member=data, mode="new")
            flash(f"Added {data['full_name']} to the member list.", "success")
            return redirect(url_for("admin_members"))
        return render_template("admin/member_form.html", member=None, mode="new")

    @app.route("/admin/members/<int:member_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_member_edit(member_id):
        db = db_module.get_db()
        existing_res = db.table("members").select("*").eq("id", member_id).execute()
        existing = existing_res.data[0] if existing_res.data else None
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
                db.table("members").update(data).eq("id", member_id).execute()
            except db_module.APIError as e:
                if not db_module.is_unique_violation(e):
                    raise
                flash("A member with that email already exists.", "error")
                return render_template("admin/member_form.html", member=data, mode="edit", member_id=member_id)
            flash(f"Updated {data['full_name']}.", "success")
            return redirect(url_for("admin_members"))

        return render_template("admin/member_form.html", member=existing, mode="edit", member_id=member_id)

    @app.route("/admin/members/<int:member_id>/delete", methods=["POST"])
    @admin_required
    def admin_member_delete(member_id):
        db = db_module.get_db()
        member_res = db.table("members").select("full_name").eq("id", member_id).execute()
        member = member_res.data[0] if member_res.data else None
        db.table("members").delete().eq("id", member_id).execute()
        if member:
            flash(f"Removed {member['full_name']} from the member list.", "success")
        return redirect(url_for("admin_members"))


def _digits(value):
    return "".join(ch for ch in value if ch.isdigit())


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
    if not _digits(data["phone"]):
        return "A phone number is required -- the member logs in with it as their password."
    if not data["join_date"]:
        return "Join date is required."
    return None


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
