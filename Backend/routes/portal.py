from datetime import date
import re
from urllib.parse import urlparse
from flask import Blueprint, current_app, jsonify, request
from mysql.connector import IntegrityError

from Backend.db import cursor
from Backend.utils import json_error, require_csrf, require_role, validated_text

bp = Blueprint("portal", __name__, url_prefix="/api/portal")


def _profile(role, user_id):
    if role == "student":
        sql = """SELECT id, student_id AS account_id, full_name, father_name, mother_name,
                        date_of_birth, gender, phone, email, address, city, admission_date, status
                 FROM students WHERE user_id = %s"""
    else:
        sql = """SELECT id, employee_id AS account_id, full_name, phone, email, address,
                        designation, department, joining_date, status
                 FROM employees WHERE user_id = %s"""
    with cursor() as db:
        db.execute(sql, (user_id,))
        return db.fetchone()


@bp.get("/overview")
@require_role("student", "employee")
def overview():
    role = request.current_user["role"]
    profile = _profile(role, request.current_user["id"])
    if not profile:
        return json_error("Profile not found.", 404)
    if role == "student":
        with cursor() as db:
            db.execute(
                """SELECT c.id, c.course_code, c.name, c.duration_months, c.fee,
                          sc.start_date, e.full_name AS instructor_name
                   FROM student_courses sc JOIN courses c ON c.id = sc.course_id
                   LEFT JOIN employees e ON e.id = sc.employee_id
                   WHERE sc.student_id = %s AND sc.status = 'active'
                   ORDER BY sc.created_at DESC LIMIT 1""",
                (profile["id"],),
            )
            course = db.fetchone()
            db.execute(
                """SELECT COUNT(*) AS total,
                          SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) AS present
                   FROM attendance WHERE student_id = %s""",
                (profile["id"],),
            )
            attendance = db.fetchone()
            db.execute(
                """SELECT COUNT(DISTINCT a.id) AS count
                   FROM assignments a
                   JOIN student_courses sc ON sc.course_id = a.course_id
                   WHERE sc.student_id = %s AND sc.status = 'active' AND a.status = 'active'""",
                (profile["id"],),
            )
            assignments = db.fetchone()["count"]
            db.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total_fee, COALESCE(SUM(paid_amount), 0) AS paid, "
                "COALESCE(SUM(due_amount), 0) AS due FROM fees WHERE student_id = %s",
                (profile["id"],),
            )
            fees = db.fetchone()
            db.execute(
                """SELECT a.id, a.title, a.body, a.published_at FROM announcements a
                   LEFT JOIN student_courses sc ON sc.course_id = a.course_id
                   WHERE a.audience IN ('all', 'student') AND (a.course_id IS NULL OR sc.student_id = %s)
                   ORDER BY a.published_at DESC LIMIT 5""",
                (profile["id"],),
            )
            announcements = db.fetchall()
        total = attendance["total"] or 0
        present = attendance["present"] or 0
        return jsonify(
            profile=profile,
            course=course,
            attendance={"total": total, "present": present, "percentage": round(present * 100 / total) if total else 0},
            assignment_count=assignments,
            fees=fees,
            announcements=announcements,
        )

    with cursor() as db:
        db.execute("SELECT COUNT(*) AS count FROM employee_courses WHERE employee_id = %s", (profile["id"],))
        course_count = db.fetchone()["count"]
        db.execute("SELECT COUNT(*) AS count FROM student_courses WHERE employee_id = %s AND status = 'active'", (profile["id"],))
        student_count = db.fetchone()["count"]
        # An employee sees assignments for the courses they are assigned to,
        # including ones created by the admin.
        db.execute(
            """SELECT COUNT(DISTINCT a.id) AS count
               FROM assignments a
               JOIN employee_courses ec ON ec.course_id = a.course_id
               WHERE ec.employee_id = %s AND a.status = 'active'""",
            (profile["id"],),
        )
        assignment_count = db.fetchone()["count"]
        db.execute(
            """SELECT a.id, a.title, a.body, a.published_at
               FROM announcements a
               LEFT JOIN employee_courses ec
                 ON ec.course_id = a.course_id AND ec.employee_id = %s
               WHERE a.audience IN ('all', 'employee')
                 AND (a.course_id IS NULL OR ec.employee_id IS NOT NULL)
               ORDER BY a.published_at DESC LIMIT 5""",
            (profile["id"],),
        )
        announcements = db.fetchall()
    return jsonify(
        profile=profile,
        assigned_courses=course_count,
        assigned_students=student_count,
        assignments=assignment_count,
        announcements=announcements,
    )


@bp.get("/profile")
@require_role("student", "employee")
def profile():
    result = _profile(request.current_user["role"], request.current_user["id"])
    if not result:
        return json_error("Profile not found.", 404)
    return jsonify(profile=result)


@bp.put("/profile")
@require_role("student", "employee")
@require_csrf
def update_profile():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_error("A JSON object is required.", 400)
    try:
        updates = {
            field: validated_text(data, field, required=False, max_length=limit)
            for field, limit in (("phone", 30), ("email", 254), ("address", 2000))
            if field in data
        }
    except ValueError as error:
        return json_error(str(error), 400)
    if not updates:
        return json_error("Provide at least one editable profile field.", 400)
    if updates.get("phone") and not re.fullmatch(r"\+?[0-9()\-\s]{7,20}", updates["phone"]):
        return json_error("Phone number is invalid.", 400)
    if updates.get("email") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", updates["email"]):
        return json_error("Email address is invalid.", 400)
    role = request.current_user["role"]
    table = "students" if role == "student" else "employees"
    try:
        with cursor() as db:
            db.execute(f"SELECT id FROM {table} WHERE user_id = %s", (request.current_user["id"],))
            if not db.fetchone():
                return json_error("Profile not found.", 404)
            assignments = ", ".join(f"{field} = %s" for field in updates)
            db.execute(
                f"UPDATE {table} SET {assignments} WHERE user_id = %s",
                (*updates.values(), request.current_user["id"]),
            )
            db.connection.commit()
    except Exception:
        current_app.logger.exception("Profile update failed")
        return json_error("The service is temporarily unavailable.", 503)
    return jsonify(message="Profile updated.")


@bp.get("/courses")
@require_role("student", "employee")
def my_courses():
    role = request.current_user["role"]
    profile = _profile(role, request.current_user["id"])
    if not profile:
        return json_error("Profile not found.", 404)
    with cursor() as db:
        if role == "student":
            db.execute(
                """SELECT c.id, c.course_code, c.name, c.description, c.duration_months, c.fee,
                          sc.status, sc.start_date, e.full_name AS instructor_name
                   FROM student_courses sc JOIN courses c ON c.id = sc.course_id
                   LEFT JOIN employees e ON e.id = sc.employee_id
                   WHERE sc.student_id = %s ORDER BY sc.created_at DESC""",
                (profile["id"],),
            )
        else:
            db.execute(
                """SELECT c.id, c.course_code, c.name, c.description, c.duration_months, c.fee
                   FROM employee_courses ec JOIN courses c ON c.id = ec.course_id
                   WHERE ec.employee_id = %s AND c.status = 'active' ORDER BY c.name""",
                (profile["id"],),
            )
        return jsonify(courses=db.fetchall())


@bp.get("/students")
@require_role("employee")
def assigned_students():
    search = request.args.get("search", "").strip()
    course_value = request.args.get("course_id", "").strip()
    try:
        course_id = int(course_value) if course_value else None
    except ValueError:
        return json_error("Course filter is invalid.", 400)
    if course_id is not None and course_id < 1:
        return json_error("Course filter is invalid.", 400)
    search = search[:100]
    with cursor() as db:
        db.execute(
            """SELECT s.id, s.student_id, s.full_name, s.phone, s.email, s.status,
                      c.id AS course_id, c.name AS course_name,
                      COUNT(a.id) AS attendance_total,
                      COALESCE(SUM(a.status = 'present'), 0) AS attendance_present,
                      CASE WHEN COUNT(a.id) = 0 THEN 0
                           ELSE ROUND(SUM(a.status = 'present') * 100 / COUNT(a.id))
                      END AS attendance_percentage
               FROM student_courses sc
               JOIN students s ON s.id = sc.student_id
               JOIN courses c ON c.id = sc.course_id
               LEFT JOIN attendance a ON a.student_id = s.id AND a.course_id = c.id
               WHERE sc.employee_id = %s AND sc.status = 'active' AND s.status = 'active'
                 AND (%s = '' OR s.student_id LIKE %s OR s.full_name LIKE %s
                      OR s.phone LIKE %s OR s.email LIKE %s)
                 AND (%s IS NULL OR c.id = %s)
               GROUP BY s.id, c.id
               ORDER BY s.full_name""",
            (
                _profile("employee", request.current_user["id"])["id"],
                search, f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%",
                course_id, course_id,
            ),
        )
        return jsonify(students=db.fetchall())


@bp.get("/students/search")
@require_role("employee")
def search_students():
    """Scoped autocomplete: an employee can only find their own students."""
    term = request.args.get("q", "").strip()[:100]
    try:
        limit = max(1, min(int(request.args.get("limit", 15)), 20))
    except ValueError:
        limit = 15
    like = f"%{term}%"
    with cursor() as db:
        db.execute(
            """SELECT DISTINCT s.id, s.student_id, s.full_name, s.email, s.phone,
                      c.name AS course_name
               FROM student_courses sc
               JOIN students s ON s.id = sc.student_id
               JOIN courses c ON c.id = sc.course_id
               WHERE sc.employee_id = (SELECT id FROM employees WHERE user_id = %s)
                 AND sc.status = 'active' AND s.status = 'active'
                 AND (%s = '' OR s.student_id LIKE %s OR s.full_name LIKE %s
                      OR s.email LIKE %s OR s.phone LIKE %s)
               ORDER BY s.full_name LIMIT %s""",
            (request.current_user["id"], term, like, like, like, like, limit),
        )
        return jsonify(students=db.fetchall())


@bp.get("/attendance")
@require_role("student", "employee")
def attendance():
    """Read-only. Staff see their own attendance; students see their own class record."""
    role = request.current_user["role"]
    profile = _profile(role, request.current_user["id"])
    with cursor() as db:
        if role == "student":
            db.execute(
                """SELECT a.attendance_date, a.status, a.remarks, c.name AS course_name
                   FROM attendance a JOIN courses c ON c.id = a.course_id
                   WHERE a.student_id = %s ORDER BY a.attendance_date DESC LIMIT 500""",
                (profile["id"],),
            )
        else:
            db.execute(
                """SELECT ea.attendance_date, ea.status, ea.remarks, NULL AS course_name,
                          NULL AS student_id, NULL AS full_name
                   FROM employee_attendance ea
                   WHERE ea.employee_id = %s ORDER BY ea.attendance_date DESC LIMIT 500""",
                (profile["id"],),
            )
        rows = db.fetchall()
        for row in rows:
            # MySQL DATE columns arrive as datetime objects; send plain YYYY-MM-DD
            # so the browser renders an ISO date rather than a full timestamp.
            row["attendance_date"] = str(row["attendance_date"])
        return jsonify(attendance=rows)


@bp.get("/assignments")
@require_role("student", "employee")
def assignments():
    """Assignments filtered by the courses each role is actually attached to."""
    role = request.current_user["role"]
    profile = _profile(role, request.current_user["id"])
    today = date.today()
    with cursor() as db:
        if role == "student":
            db.execute(
                """SELECT DISTINCT a.id, a.title, a.description, a.due_date, a.status,
                          a.attachment AS resource_url, c.name AS course_name
                   FROM assignments a
                   JOIN courses c ON c.id = a.course_id
                   JOIN student_courses sc ON sc.course_id = a.course_id
                   WHERE sc.student_id = %s AND sc.status = 'active' AND a.status = 'active'
                   ORDER BY a.due_date IS NULL, a.due_date, a.title""",
                (profile["id"],),
            )
        else:
            db.execute(
                """SELECT DISTINCT a.id, a.title, a.description, a.due_date, a.status,
                          a.attachment AS resource_url, c.name AS course_name
                   FROM assignments a
                   JOIN courses c ON c.id = a.course_id
                   JOIN employee_courses ec ON ec.course_id = a.course_id
                   WHERE ec.employee_id = %s AND a.status = 'active'
                   ORDER BY a.due_date IS NULL, a.due_date, a.title""",
                (profile["id"],),
            )
        rows = db.fetchall()
    # 'overdue' is derived, never stored.
    for row in rows:
        if row["due_date"]:
            row["due_date"] = str(row["due_date"])
        row["overdue"] = bool(row["due_date"]) and row["due_date"] < today.isoformat()
    return jsonify(assignments=rows)


@bp.post("/assignments")
@require_role("employee")
@require_csrf
def create_assignment():
    data = request.get_json(silent=True) or {}
    try:
        title = validated_text(data, "title", max_length=200)
        description = validated_text(data, "description", required=False, max_length=10000)
        course_id = data.get("course_id")
        due_date = date.fromisoformat(data["due_date"]) if data.get("due_date") else None
    except (ValueError, TypeError):
        return json_error("Assignment details are invalid.", 400)
    if not isinstance(course_id, int) or course_id < 1:
        return json_error("A valid course is required.", 400)
    attachment = data.get("attachment")
    if attachment is not None and attachment != "" and not _is_http_url(attachment, 500):
        return json_error("Attachment URL is invalid.", 400)
    with cursor() as db:
        db.execute(
            "SELECT course_id FROM employee_courses WHERE employee_id = "
            "(SELECT id FROM employees WHERE user_id = %s) AND course_id = %s",
            (request.current_user["id"], course_id),
        )
        if not db.fetchone():
            return json_error("You are not assigned to this course.", 403)
        db.execute(
            "INSERT INTO assignments (title, description, course_id, created_by, due_date, attachment) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (title, description, course_id, request.current_user["id"], due_date, attachment or None),
        )
        db.connection.commit()
        assignment_id = db.lastrowid
    return jsonify(assignment_id=assignment_id, message="Assignment created successfully."), 201


@bp.put("/assignments/<int:assignment_id>")
@require_role("employee")
@require_csrf
def update_assignment(assignment_id):
    """Employees may only change assignments in courses they are assigned to."""
    data = request.get_json(silent=True) or {}
    try:
        title = validated_text(data, "title", max_length=200)
        description = validated_text(data, "description", required=False, max_length=10000)
        due_date = date.fromisoformat(data["due_date"]) if data.get("due_date") else None
    except (ValueError, TypeError):
        return json_error("Assignment details are invalid.", 400)
    with cursor() as db:
        db.execute(
            """SELECT a.id FROM assignments a
               JOIN employee_courses ec ON ec.course_id = a.course_id
               JOIN employees e ON e.id = ec.employee_id
               WHERE a.id = %s AND e.user_id = %s AND a.created_by = %s""",
            (assignment_id, request.current_user["id"], request.current_user["id"]),
        )
        if not db.fetchone():
            return json_error("You cannot edit this assignment.", 403)
        db.execute(
            "UPDATE assignments SET title = %s, description = %s, due_date = %s WHERE id = %s",
            (title, description, due_date, assignment_id),
        )
        db.connection.commit()
    return jsonify(message="Assignment updated.")


@bp.delete("/assignments/<int:assignment_id>")
@require_role("employee")
@require_csrf
def delete_assignment(assignment_id):
    connection = None
    try:
        with cursor() as db:
            connection = db.connection
            connection.start_transaction()
            db.execute(
                """SELECT a.id FROM assignments a
                   JOIN employee_courses ec ON ec.course_id = a.course_id
                   JOIN employees e ON e.id = ec.employee_id
                   WHERE a.id = %s AND e.user_id = %s AND a.created_by = %s""",
                (assignment_id, request.current_user["id"], request.current_user["id"]),
            )
            if not db.fetchone():
                connection.rollback()
                return json_error("You cannot delete this assignment.", 403)
            db.execute("DELETE FROM assignments WHERE id = %s", (assignment_id,))
            connection.commit()
    except Exception as error:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception("Assignment delete failed", exc_info=error)
        return json_error("The request could not be completed.", 503)
    return jsonify(message="Assignment deleted.")


@bp.get("/materials")
@require_role("student", "employee")
def materials():
    role = request.current_user["role"]
    profile = _profile(role, request.current_user["id"])
    with cursor() as db:
        if role == "student":
            db.execute(
                """SELECT DISTINCT m.id, m.title, m.description, m.file_url, m.created_at, c.name AS course_name
                   FROM study_materials m JOIN courses c ON c.id = m.course_id
                   JOIN student_courses sc ON sc.course_id = c.id
                   WHERE sc.student_id = %s AND sc.status = 'active' ORDER BY m.created_at DESC""",
                (profile["id"],),
            )
        else:
            db.execute(
                """SELECT m.id, m.title, m.description, m.file_url, m.created_at, c.name AS course_name
                   FROM study_materials m JOIN courses c ON c.id = m.course_id
                   WHERE m.uploaded_by = %s ORDER BY m.created_at DESC""",
                (request.current_user["id"],),
            )
        return jsonify(materials=db.fetchall())


@bp.post("/materials")
@require_role("employee")
@require_csrf
def create_material():
    data = request.get_json(silent=True) or {}
    try:
        title = validated_text(data, "title", max_length=180)
        description = validated_text(data, "description", required=False, max_length=5000)
        file_url = validated_text(data, "file_url", max_length=500)
    except ValueError as error:
        return json_error(str(error), 400)
    if not _is_http_url(file_url, 500):
        return json_error("Material URL must use HTTP or HTTPS.", 400)
    course_id = data.get("course_id")
    if not isinstance(course_id, int) or course_id < 1:
        return json_error("A valid course is required.", 400)
    with cursor() as db:
        db.execute(
            "SELECT course_id FROM employee_courses WHERE employee_id = "
            "(SELECT id FROM employees WHERE user_id = %s) AND course_id = %s",
            (request.current_user["id"], course_id),
        )
        if not db.fetchone():
            return json_error("You are not assigned to this course.", 403)
        db.execute(
            "INSERT INTO study_materials (title, description, course_id, uploaded_by, file_url) "
            "VALUES (%s, %s, %s, %s, %s)",
            (title, description, course_id, request.current_user["id"], file_url),
        )
        db.connection.commit()
        material_id = db.lastrowid
    return jsonify(material_id=material_id), 201


def _is_http_url(value, max_length):
    if not isinstance(value, str) or len(value) > max_length:
        return False
    parsed = urlparse(value)
    return parsed.scheme in ("https", "http") and bool(parsed.netloc)


@bp.get("/announcements")
@require_role("student", "employee")
def announcements():
    role = request.current_user["role"]
    profile = _profile(role, request.current_user["id"])
    with cursor() as db:
        if role == "student":
            db.execute(
                """SELECT DISTINCT a.id, a.title, a.body, a.published_at, c.name AS course_name
                   FROM announcements a LEFT JOIN courses c ON c.id = a.course_id
                   LEFT JOIN student_courses sc ON sc.course_id = a.course_id
                   WHERE a.audience IN ('all', 'student') AND (a.course_id IS NULL OR sc.student_id = %s)
                   ORDER BY a.published_at DESC LIMIT 500""",
                (profile["id"],),
            )
        else:
            db.execute(
                """SELECT a.id, a.title, a.body, a.published_at, c.name AS course_name
                   FROM announcements a
                   LEFT JOIN courses c ON c.id = a.course_id
                   LEFT JOIN employee_courses ec
                     ON ec.course_id = a.course_id AND ec.employee_id = %s
                   WHERE a.audience IN ('all', 'employee')
                     AND (a.course_id IS NULL OR ec.employee_id IS NOT NULL)
                   ORDER BY a.published_at DESC LIMIT 500""",
                (profile["id"],),
            )
        return jsonify(announcements=db.fetchall())


@bp.post("/announcements")
@require_role("employee")
@require_csrf
def create_announcement():
    data = request.get_json(silent=True) or {}
    try:
        title = validated_text(data, "title", max_length=180)
        body = validated_text(data, "body", max_length=5000)
    except ValueError as error:
        return json_error(str(error), 400)
    course_id = data.get("course_id")
    audience = data.get("audience", "all")
    if audience not in ("all", "student", "employee") or (course_id is not None and not isinstance(course_id, int)):
        return json_error("Announcement audience or course is invalid.", 400)
    if course_id is None and audience != "employee":
        return json_error("Select an assigned course to notify students.", 400)
    with cursor() as db:
        if course_id is not None:
            db.execute(
                "SELECT course_id FROM employee_courses WHERE employee_id = "
                "(SELECT id FROM employees WHERE user_id = %s) AND course_id = %s",
                (request.current_user["id"], course_id),
            )
            if not db.fetchone():
                return json_error("You are not assigned to this course.", 403)
        db.execute(
            "INSERT INTO announcements (title, body, audience, course_id, created_by) VALUES (%s, %s, %s, %s, %s)",
            (title, body, audience, course_id, request.current_user["id"]),
        )
        db.connection.commit()
    return jsonify(message="Announcement created."), 201


@bp.get("/fees")
@require_role("student")
def fees():
    profile = _profile("student", request.current_user["id"])
    with cursor() as db:
        db.execute(
            """SELECT f.id, c.name AS course_name, f.amount, f.paid_amount, f.due_amount,
                      f.payment_date, f.payment_status, f.remarks
               FROM fees f LEFT JOIN courses c ON c.id = f.course_id
               WHERE f.student_id = %s ORDER BY f.created_at DESC""",
            (profile["id"],),
        )
        return jsonify(fees=db.fetchall())


@bp.get("/results")
@require_role("student")
def results():
    profile = _profile("student", request.current_user["id"])
    with cursor() as db:
        db.execute(
            """SELECT r.id, r.subject, r.marks, r.grade, r.exam_date, c.name AS course_name
               FROM results r JOIN courses c ON c.id = r.course_id
               WHERE r.student_id = %s ORDER BY r.exam_date DESC""",
            (profile["id"],),
        )
        return jsonify(results=db.fetchall())
