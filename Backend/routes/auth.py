from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.security import check_password_hash

from Backend.db import cursor
from Backend.extensions import limiter
from Backend.utils import (
    hash_password,
    json_error,
    new_csrf_token,
    require_csrf,
    require_role,
    validate_password,
    verify_password,
)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _user_payload(user):
    profile = None
    if user["role"] == "student":
        with cursor() as db:
            db.execute(
                """SELECT student_id, full_name, phone, email
                   FROM students WHERE user_id = %s""",
                (user["id"],),
            )
            profile = db.fetchone()
    elif user["role"] == "employee":
        with cursor() as db:
            db.execute(
                """SELECT employee_id, full_name, phone, email, designation
                   FROM employees WHERE user_id = %s""",
                (user["id"],),
            )
            profile = db.fetchone()
    elif user["role"] == "admin":
        with cursor() as db:
            db.execute(
                "SELECT full_name FROM admins WHERE user_id = %s",
                (user["id"],),
            )
            profile = db.fetchone()
    return {
        "id": user["id"],
        "login_id": user["login_id"],
        "role": user["role"],
        "must_change_password": bool(user["must_change_password"]),
        "profile": profile,
    }


@bp.post("/login")
@limiter.limit(lambda: current_app.config["LOGIN_RATE_LIMIT"])
def login():
    payload = request.get_json(silent=True) or {}
    identifier = payload.get("identifier")
    password = payload.get("password")
    expected_role = payload.get("role")
    if not isinstance(identifier, str) or not isinstance(password, str):
        return json_error("Invalid ID or password.", 401)
    if expected_role not in ("admin", "student", "employee"):
        return json_error("Invalid ID or password.", 401)

    try:
        with cursor() as db:
            db.execute(
                """SELECT id, login_id, password_hash, role, status, auth_version,
                          must_change_password
                   FROM users WHERE login_id = %s""",
                (identifier.strip(),),
            )
            user = db.fetchone()
    except Exception:
        current_app.logger.exception("Database unavailable during login")
        return json_error("Login service is temporarily unavailable.", 503)

    valid = user and user["status"] == "active" and user["role"] == expected_role
    if not valid or not check_password_hash(user["password_hash"], password):
        return json_error("Invalid ID or password.", 401)

    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    session["auth_version"] = user["auth_version"]
    session["csrf_token"] = new_csrf_token()
    with cursor() as db:
        db.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s", (user["id"],))
        db.connection.commit()
    return jsonify(user=_user_payload(user), csrf_token=session["csrf_token"])


@bp.post("/logout")
@require_role("admin", "student", "employee")
@require_csrf
def logout():
    session.clear()
    response = jsonify(message="Logged out.")
    response.delete_cookie(current_app.config.get("SESSION_COOKIE_NAME", "session"))
    return response


@bp.get("/me")
@require_role("admin", "student", "employee")
def me():
    with cursor() as db:
        db.execute(
            """SELECT id, login_id, role, auth_version, must_change_password
               FROM users WHERE id = %s""",
            (request.current_user["id"],),
        )
        user = db.fetchone()
    return jsonify(user=_user_payload(user), csrf_token=new_csrf_token())


@bp.post("/change-password")
@require_role("admin", "student", "employee")
@require_csrf
def change_password():
    payload = request.get_json(silent=True) or {}
    old_password = payload.get("current_password")
    new_password = payload.get("new_password")
    confirm_password = payload.get("confirm_password")
    if not isinstance(old_password, str) or not isinstance(new_password, str):
        return json_error("Current and new passwords are required.", 400)
    if new_password != confirm_password:
        return json_error("Passwords do not match.", 400)
    try:
        validate_password(new_password)
    except ValueError as error:
        return json_error(str(error), 400)
    try:
        with cursor() as db:
            db.execute("SELECT password_hash FROM users WHERE id = %s", (request.current_user["id"],))
            user = db.fetchone()
            if not user or not verify_password(user["password_hash"], old_password):
                return json_error("Current password is incorrect.", 400)
            db.execute(
                """UPDATE users SET password_hash = %s, auth_version = auth_version + 1,
                          must_change_password = FALSE WHERE id = %s""",
                (hash_password(new_password), request.current_user["id"]),
            )
            db.execute("SELECT auth_version FROM users WHERE id = %s", (request.current_user["id"],))
            session["auth_version"] = db.fetchone()["auth_version"]
            db.connection.commit()
    except Exception:
        current_app.logger.exception("Password update failed")
        return json_error("The service is temporarily unavailable.", 503)
    return jsonify(message="Password changed.")
