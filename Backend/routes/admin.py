from datetime import date
from decimal import Decimal, InvalidOperation
import re
import secrets

from flask import Blueprint, current_app, jsonify, request
from mysql.connector import IntegrityError

from Backend.db import cursor
from Backend.utils import (
    generate_memorable_password,
    hash_password,
    json_error,
    require_csrf,
    require_role,
    validate_password,
    validated_text,
)

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("A JSON object is required.")
    return data


def _optional_date(data, field):
    value = validated_text(data, field, required=False, max_length=10)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field.replace('_', ' ').capitalize()} must use YYYY-MM-DD format.") from error


def _password(data):
    password = data.get("password")
    confirm_password = data.get("confirm_password")
    if not isinstance(password, str) or not password:
        raise ValueError("Password is required.")
    if not isinstance(confirm_password, str) or confirm_password == "":
        raise ValueError("Password confirmation is required.")
    if confirm_password != password:
        raise ValueError("Passwords do not match.")
    return validate_password(password)


def _validate_contact(field, value):
    if value is None:
        return
    if field == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise ValueError("Email address is invalid.")
    if field == "phone" and not re.fullmatch(r"\+?[0-9()\-\s]{7,20}", value):
        raise ValueError("Phone number is invalid.")


def _commit_error(error):
    current_app.logger.exception("Admin operation failed", exc_info=error)
    return json_error("The request could not be completed.", 503)


def _search_term():
    """Read `q` from the query string and constrain it before it reaches SQL."""
    term = request.args.get("q", "").strip()
    if not term:
        return ""
    return term[:100]


def _search_limit(default=15, maximum=20):
    """Autocomplete never returns more than a screenful of rows."""
    try:
        limit = int(request.args.get("limit", default))
    except ValueError:
        return default
    return max(1, min(limit, maximum))


@bp.get("/search/students")
@require_role("admin", "employee")
def search_students():
    """Database-backed student autocomplete. Never loads the full student list."""
    term = _search_term()
    limit = _search_limit()
    course_value = request.args.get("course_id", "").strip()
    try:
        course_id = int(course_value) if course_value else None
    except ValueError:
        return json_error("Course filter is invalid.", 400)

    role = request.current_user["role"]
    conditions = ["s.status = 'active'"]
    params = []
    if term:
        like = f"%{term}%"
        conditions.append(
            "(s.student_id LIKE %s OR s.full_name LIKE %s"
            " OR s.email LIKE %s OR s.phone LIKE %s)"
        )
        params.extend((like, like, like, like))
    # An employee may only search students enrolled in their own courses.
    scope = (
        "SELECT sc.student_id FROM student_courses sc JOIN employee_courses ec"
        " ON ec.course_id = sc.course_id"
        " JOIN employees e ON e.id = ec.employee_id"
        " WHERE e.user_id = %s AND sc.status = 'active'"
    ) if role == "employee" else None
    if course_id is not None:
        conditions.append("EXISTS (SELECT 1 FROM student_courses scf WHERE scf.student_id = s.id AND scf.course_id = %s)")
        params.append(course_id)
    if scope:
        conditions.append(f"s.id IN ({scope})")
        params.append(request.current_user["id"])

    with cursor() as db:
        db.execute(
            f"""SELECT s.id, s.student_id, s.full_name, s.email, s.phone, s.status,
                       (SELECT c.name FROM student_courses sc2 JOIN courses c ON c.id = sc2.course_id
                        WHERE sc2.student_id = s.id AND sc2.status = 'active'
                        ORDER BY sc2.created_at DESC LIMIT 1) AS course_name
                FROM students s
                WHERE {' AND '.join(conditions)}
                ORDER BY s.full_name LIMIT %s""",
            (*params, limit),
        )
        return jsonify(students=db.fetchall())


@bp.get("/search/employees")
@require_role("admin")
def search_employees():
    """Database-backed employee autocomplete (ID, name, email, phone, designation)."""
    term = _search_term()
    limit = _search_limit()
    conditions = ["1 = 1"]
    params = []
    if term:
        like = f"%{term}%"
        conditions.append(
            "(e.employee_id LIKE %s OR e.full_name LIKE %s OR e.email LIKE %s"
            " OR e.phone LIKE %s OR e.designation LIKE %s OR e.department LIKE %s)"
        )
        params.extend((like, like, like, like, like, like))
    with cursor() as db:
        db.execute(
            f"""SELECT e.id, e.employee_id, e.full_name, e.email, e.phone,
                       e.designation, e.department, e.status
                FROM employees e
                WHERE {' AND '.join(conditions)}
                ORDER BY e.full_name LIMIT %s""",
            (*params, limit),
        )
        return jsonify(employees=db.fetchall())


@bp.get("/search/courses")
@require_role("admin", "employee")
def search_courses():
    term = _search_term()
    limit = _search_limit()
    conditions = ["c.status = 'active'"]
    params = []
    if term:
        like = f"%{term}%"
        conditions.append("(c.name LIKE %s OR c.course_code LIKE %s)")
        params.extend((like, like))
    if request.current_user["role"] == "employee":
        conditions.append(
            """EXISTS (SELECT 1 FROM employee_courses ec JOIN employees e ON e.id = ec.employee_id
                       WHERE ec.course_id = c.id AND e.user_id = %s)"""
        )
        params.append(request.current_user["id"])
    with cursor() as db:
        db.execute(
            f"""SELECT c.id, c.course_code, c.name
                FROM courses c WHERE {' AND '.join(conditions)}
                ORDER BY c.name LIMIT %s""",
            (*params, limit),
        )
        return jsonify(courses=db.fetchall())


@bp.get("/search/assignments")
@require_role("admin")
def search_assignments():
    term = _search_term()
    limit = _search_limit()
    like = f"%{term}%"
    with cursor() as db:
        db.execute(
            """SELECT a.id, a.title, a.status, a.due_date, c.name AS course_name
               FROM assignments a JOIN courses c ON c.id = a.course_id
               WHERE %s = '' OR a.title LIKE %s OR c.name LIKE %s
               ORDER BY a.created_at DESC LIMIT %s""",
            (term, like, like, limit),
        )
        return jsonify(assignments=db.fetchall())


@bp.get("/dashboard")
@require_role("admin")
def dashboard():
    with cursor() as db:
        db.execute(
            """SELECT
              (SELECT COUNT(*) FROM students) AS total_students,
              (SELECT COUNT(*) FROM employees) AS total_employees,
              (SELECT COUNT(*) FROM courses WHERE status = 'active') AS total_courses,
              (SELECT COUNT(*) FROM students WHERE status = 'active') AS active_students,
              (SELECT COUNT(*) FROM employees WHERE status = 'active') AS active_employees,
              (SELECT COALESCE(SUM(due_amount), 0) FROM fees WHERE payment_status != 'paid') AS pending_fees"""
        )
        stats = db.fetchone()
    return jsonify(stats=stats)


@bp.get("/students")
@require_role("admin")
def students():
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()
    course_value = request.args.get("course_id", "").strip()
    if status and status not in ("active", "inactive"):
        return json_error("Student status filter is invalid.", 400)
    try:
        course_id = int(course_value) if course_value else None
    except ValueError:
        return json_error("Course filter is invalid.", 400)
    if course_id is not None and course_id < 1:
        return json_error("Course filter is invalid.", 400)
    with cursor() as db:
        db.execute(
            """SELECT s.id, s.student_id, s.full_name, s.phone, s.email, s.status,
                      sc.course_id, c.name AS course_name, s.admission_date
               FROM students s
               LEFT JOIN student_courses sc ON sc.student_id = s.id AND sc.status = 'active'
               LEFT JOIN courses c ON c.id = sc.course_id
               WHERE (%s = '' OR s.full_name LIKE %s OR s.student_id LIKE %s
                      OR s.phone LIKE %s OR s.email LIKE %s)
                 AND (%s = '' OR s.status = %s)
                 AND (%s IS NULL OR sc.course_id = %s)
               ORDER BY s.created_at DESC LIMIT 500""",
            (
                search, f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%",
                status, status, course_id, course_id,
            ),
        )
        return jsonify(students=db.fetchall())


@bp.post("/students")
@require_role("admin")
@require_csrf
def create_student():
    try:
        data = _payload()
        full_name = validated_text(data, "full_name", max_length=150)
        password = _password(data)
        course_id = data.get("course_id")
        if not isinstance(course_id, int) or course_id < 1:
            return json_error("A valid course is required.", 400)
        status = data.get("status", "active")
        if status not in ("active", "inactive"):
            return json_error("Status must be active or inactive.", 400)
        fields = {
            "father_name": validated_text(data, "father_name", required=False, max_length=150),
            "mother_name": validated_text(data, "mother_name", required=False, max_length=150),
            "gender": validated_text(data, "gender", required=False, max_length=30),
            "phone": validated_text(data, "phone", required=False, max_length=30),
            "email": validated_text(data, "email", required=False, max_length=254),
            "address": validated_text(data, "address", required=False, max_length=2000),
            "city": validated_text(data, "city", required=False, max_length=100),
        }
        _validate_contact("phone", fields["phone"])
        _validate_contact("email", fields["email"])
        dob = _optional_date(data, "date_of_birth")
        admission_date = _optional_date(data, "admission_date")
        employee_pk = data.get("employee_id")
        if employee_pk is not None and (not isinstance(employee_pk, int) or employee_pk < 1):
            return json_error("Employee assignment is invalid.", 400)
        temporary_key = f"pending-{secrets.token_hex(16)}"
        with cursor() as db:
            connection = db.connection
            connection.start_transaction()
            db.execute("SELECT id FROM courses WHERE id = %s AND status = 'active'", (course_id,))
            if not db.fetchone():
                connection.rollback()
                return json_error("Course not found or inactive.", 404)
            if employee_pk is not None:
                db.execute(
                    """SELECT e.id FROM employees e JOIN employee_courses ec ON ec.employee_id = e.id
                       WHERE e.id = %s AND ec.course_id = %s AND e.status = 'active'""",
                    (employee_pk, course_id),
                )
                if not db.fetchone():
                    connection.rollback()
                    return json_error("Employee is not assigned to this course.", 400)
            db.execute(
                """INSERT INTO users
                   (login_id, password_hash, role, status, must_change_password)
                   VALUES (%s, %s, 'student', %s, TRUE)""",
                (temporary_key, hash_password(password), status),
            )
            user_id = db.lastrowid
            db.execute(
                """INSERT INTO students
                   (user_id, student_id, full_name, father_name, mother_name, date_of_birth,
                    gender, phone, email, address, city, admission_date, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    user_id, temporary_key, full_name, fields["father_name"], fields["mother_name"],
                    dob, fields["gender"], fields["phone"], fields["email"], fields["address"],
                    fields["city"], admission_date, status,
                ),
            )
            student_row_id = db.lastrowid
            generated_id = f"DM{date.today().year}{student_row_id:04d}"
            db.execute("UPDATE students SET student_id = %s WHERE id = %s", (generated_id, student_row_id))
            db.execute("UPDATE users SET login_id = %s WHERE id = %s", (generated_id, user_id))
            db.execute(
                """INSERT INTO student_courses (student_id, course_id, employee_id, start_date, status)
                   VALUES (%s, %s, %s, %s, 'active')""",
                (student_row_id, course_id, employee_pk, admission_date),
            )
            connection.commit()
        result = {
            "student_id": generated_id,
            "login_id": generated_id,
            "full_name": full_name,
            "temporary_password": password,
        }
        return jsonify(student=result), 201
    except ValueError as error:
        return json_error(str(error), 400)
    except IntegrityError:
        return json_error("A record with one of these details already exists.", 409)
    except Exception as error:
        return _commit_error(error)


@bp.get("/students/<int:student_pk>")
@require_role("admin")
def student_detail(student_pk):
    with cursor() as db:
        db.execute(
            """SELECT s.*, sc.course_id, sc.employee_id
               FROM students s
               LEFT JOIN student_courses sc ON sc.student_id = s.id AND sc.status = 'active'
               WHERE s.id = %s LIMIT 1""",
            (student_pk,),
        )
        student = db.fetchone()
    if not student:
        return json_error("Student not found.", 404)
    student.pop("user_id", None)
    return jsonify(student=student)


@bp.put("/students/<int:student_pk>")
@require_role("admin")
@require_csrf
def update_student(student_pk):
    try:
        data = _payload()
        allowed = {
            "full_name": (150, True), "father_name": (150, False), "mother_name": (150, False),
            "gender": (30, False), "phone": (30, False), "email": (254, False),
            "address": (2000, False), "city": (100, False),
        }
        updates = {field: validated_text(data, field, required=required, max_length=length)
                   for field, (length, required) in allowed.items() if field in data}
        for field in ("phone", "email"):
            if field in updates:
                _validate_contact(field, updates[field])
        if "status" in data:
            if data["status"] not in ("active", "inactive"):
                return json_error("Status must be active or inactive.", 400)
            updates["status"] = data["status"]
        for field in ("date_of_birth", "admission_date"):
            if field in data:
                updates[field] = _optional_date(data, field)
        with cursor() as db:
            db.connection.start_transaction()
            db.execute("SELECT user_id FROM students WHERE id = %s", (student_pk,))
            student = db.fetchone()
            if not student:
                db.connection.rollback()
                return json_error("Student not found.", 404)
            if updates:
                assignments = ", ".join(f"{field} = %s" for field in updates)
                db.execute(
                    f"UPDATE students SET {assignments} WHERE id = %s",
                    (*updates.values(), student_pk),
                )
                if "status" in updates:
                    db.execute(
                        """UPDATE users SET status = %s, auth_version = auth_version + 1
                           WHERE id = %s""",
                        (updates["status"], student["user_id"]),
                    )
            if "course_id" in data:
                course_id = data["course_id"]
                if not isinstance(course_id, int) or course_id < 1:
                    db.connection.rollback()
                    return json_error("A valid course is required.", 400)
                db.execute("SELECT id FROM courses WHERE id = %s AND status = 'active'", (course_id,))
                if not db.fetchone():
                    db.connection.rollback()
                    return json_error("Course not found or inactive.", 404)
                employee_pk = data.get("employee_id")
                if employee_pk is not None:
                    if not isinstance(employee_pk, int) or employee_pk < 1:
                        db.connection.rollback()
                        return json_error("Employee assignment is invalid.", 400)
                    db.execute(
                        """SELECT e.id FROM employees e JOIN employee_courses ec ON ec.employee_id = e.id
                           WHERE e.id = %s AND ec.course_id = %s AND e.status = 'active'""",
                        (employee_pk, course_id),
                    )
                    if not db.fetchone():
                        db.connection.rollback()
                        return json_error("Employee is not assigned to this course.", 400)
                db.execute(
                    "UPDATE student_courses SET status = 'withdrawn' WHERE student_id = %s AND status = 'active'",
                    (student_pk,),
                )
                db.execute(
                    "INSERT INTO student_courses (student_id, course_id, employee_id, status) "
                    "VALUES (%s, %s, %s, 'active') "
                    "ON DUPLICATE KEY UPDATE status = 'active', employee_id = VALUES(employee_id)",
                    (student_pk, course_id, employee_pk if "employee_id" in data else None),
                )
            db.connection.commit()
        return jsonify(message="Student updated.")
    except ValueError as error:
        return json_error(str(error), 400)
    except Exception as error:
        return _commit_error(error)


@bp.post("/students/<int:student_pk>/reset-password")
@require_role("admin")
@require_csrf
def reset_student_password(student_pk):
    password = generate_memorable_password()
    with cursor() as db:
        db.execute("SELECT user_id FROM students WHERE id = %s", (student_pk,))
        student = db.fetchone()
        if not student:
            return json_error("Student not found.", 404)
        db.execute(
            """UPDATE users SET password_hash = %s, auth_version = auth_version + 1,
                      must_change_password = TRUE WHERE id = %s""",
            (hash_password(password), student["user_id"]),
        )
        db.connection.commit()
    return jsonify(temporary_password=password)


@bp.delete("/students/<int:student_pk>")
@require_role("admin")
@require_csrf
def delete_student(student_pk):
    connection = None
    try:
        if (_payload().get("confirmation") != "DELETE"):
            return json_error("Type DELETE to permanently remove this student and all associated records.", 400)
        with cursor() as db:
            db.connection.start_transaction()
            connection = db.connection
            db.execute("SELECT user_id, student_id FROM students WHERE id = %s", (student_pk,))
            student = db.fetchone()
            if not student:
                db.connection.rollback()
                return json_error("Student not found.", 404)
            db.execute(
                "DELETE FROM students WHERE id = %s",
                (student_pk,),
            )
            db.execute(
                "DELETE FROM users WHERE id = %s",
                (student["user_id"],),
            )
            db.connection.commit()
        return jsonify(message="Student and associated records permanently deleted.")
    except ValueError as error:
        return json_error(str(error), 400)
    except Exception as error:
        if connection is not None:
            connection.rollback()
        return _commit_error(error)


@bp.get("/employees")
@require_role("admin")
def employees():
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()
    if status and status not in ("active", "inactive"):
        return json_error("Employee status filter is invalid.", 400)
    course_value = request.args.get("course_id", "").strip()
    try:
        course_id = int(course_value) if course_value else None
    except ValueError:
        return json_error("Course filter is invalid.", 400)
    if course_id is not None and course_id < 1:
        return json_error("Course filter is invalid.", 400)
    with cursor() as db:
        db.execute(
            """SELECT e.id, e.employee_id, e.full_name, e.phone, e.email, e.designation,
                      e.department, e.status
               FROM employees e
               WHERE (%s = '' OR e.full_name LIKE %s OR e.employee_id LIKE %s
                      OR e.phone LIKE %s OR e.email LIKE %s)
                 AND (%s = '' OR e.status = %s)
                 AND (%s IS NULL OR EXISTS (
                     SELECT 1 FROM employee_courses ec
                     WHERE ec.employee_id = e.id AND ec.course_id = %s
                 ))
               ORDER BY e.created_at DESC LIMIT 500""",
            (
                search, f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%",
                status, status, course_id, course_id,
            ),
        )
        return jsonify(employees=db.fetchall())


@bp.post("/employees")
@require_role("admin")
@require_csrf
def create_employee():
    try:
        data = _payload()
        full_name = validated_text(data, "full_name", max_length=150)
        password = _password(data)
        status = data.get("status", "active")
        if status not in ("active", "inactive"):
            return json_error("Status must be active or inactive.", 400)
        course_ids = data.get("course_ids", [])
        if not isinstance(course_ids, list) or any(not isinstance(item, int) or item < 1 for item in course_ids):
            return json_error("Course assignments are invalid.", 400)
        course_ids = list(set(course_ids))
        if not course_ids:
            return json_error("Assign at least one course to the employee.", 400)
        phone = validated_text(data, "phone", required=False, max_length=30)
        email = validated_text(data, "email", required=False, max_length=254)
        _validate_contact("phone", phone)
        _validate_contact("email", email)
        temporary_key = f"pending-{secrets.token_hex(16)}"
        with cursor() as db:
            connection = db.connection
            connection.start_transaction()
            db.execute(
                """INSERT INTO users
                   (login_id, password_hash, role, status, must_change_password)
                   VALUES (%s, %s, 'employee', %s, TRUE)""",
                (temporary_key, hash_password(password), status),
            )
            user_id = db.lastrowid
            db.execute(
                """INSERT INTO employees
                   (user_id, employee_id, full_name, phone, email, address, designation,
                    department, joining_date, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    user_id, temporary_key, full_name,
                    phone,
                    email,
                    validated_text(data, "address", required=False, max_length=2000),
                    validated_text(data, "designation", required=False, max_length=120),
                    validated_text(data, "department", required=False, max_length=120),
                    _optional_date(data, "joining_date"), status,
                ),
            )
            employee_pk = db.lastrowid
            employee_id = f"EMP{1000 + employee_pk}"
            db.execute("UPDATE employees SET employee_id = %s WHERE id = %s", (employee_id, employee_pk))
            db.execute("UPDATE users SET login_id = %s WHERE id = %s", (employee_id, user_id))
            for course_id in course_ids:
                db.execute("SELECT id FROM courses WHERE id = %s AND status = 'active'", (course_id,))
                if not db.fetchone():
                    connection.rollback()
                    return json_error("Course assignment references an inactive course.", 400)
                db.execute(
                    "INSERT INTO employee_courses (employee_id, course_id) VALUES (%s, %s)",
                    (employee_pk, course_id),
                )
            connection.commit()
        result = {
            "employee_id": employee_id,
            "login_id": employee_id,
            "full_name": full_name,
            "temporary_password": password,
        }
        return jsonify(employee=result), 201
    except ValueError as error:
        return json_error(str(error), 400)
    except IntegrityError:
        return json_error("A record with one of these details already exists.", 409)
    except Exception as error:
        return _commit_error(error)


@bp.get("/employees/<int:employee_pk>")
@require_role("admin")
def employee_detail(employee_pk):
    with cursor() as db:
        db.execute("SELECT * FROM employees WHERE id = %s", (employee_pk,))
        employee = db.fetchone()
        if employee:
            db.execute("SELECT course_id FROM employee_courses WHERE employee_id = %s", (employee_pk,))
            employee["course_ids"] = [row["course_id"] for row in db.fetchall()]
    if not employee:
        return json_error("Employee not found.", 404)
    employee.pop("user_id", None)
    return jsonify(employee=employee)


@bp.put("/employees/<int:employee_pk>")
@require_role("admin")
@require_csrf
def update_employee(employee_pk):
    try:
        data = _payload()
        allowed = {
            "full_name": (150, True), "phone": (30, False), "email": (254, False),
            "address": (2000, False), "designation": (120, False), "department": (120, False),
        }
        updates = {field: validated_text(data, field, required=required, max_length=length)
                   for field, (length, required) in allowed.items() if field in data}
        for field in ("phone", "email"):
            if field in updates:
                _validate_contact(field, updates[field])
        if "joining_date" in data:
            updates["joining_date"] = _optional_date(data, "joining_date")
        if "status" in data:
            if data["status"] not in ("active", "inactive"):
                return json_error("Status must be active or inactive.", 400)
            updates["status"] = data["status"]
        with cursor() as db:
            db.connection.start_transaction()
            db.execute("SELECT user_id FROM employees WHERE id = %s", (employee_pk,))
            employee = db.fetchone()
            if not employee:
                db.connection.rollback()
                return json_error("Employee not found.", 404)
            if updates:
                assignments = ", ".join(f"{field} = %s" for field in updates)
                db.execute(f"UPDATE employees SET {assignments} WHERE id = %s", (*updates.values(), employee_pk))
                if "status" in updates:
                    db.execute(
                        """UPDATE users SET status = %s, auth_version = auth_version + 1
                           WHERE id = %s""",
                        (updates["status"], employee["user_id"]),
                    )
            if "course_ids" in data:
                ids = data["course_ids"]
                if not isinstance(ids, list) or any(not isinstance(item, int) or item < 1 for item in ids):
                    db.connection.rollback()
                    return json_error("Course assignments are invalid.", 400)
                db.execute("DELETE FROM employee_courses WHERE employee_id = %s", (employee_pk,))
                for course_id in set(ids):
                    db.execute("SELECT id FROM courses WHERE id = %s AND status = 'active'", (course_id,))
                    if not db.fetchone():
                        db.connection.rollback()
                        return json_error("Course assignment references an inactive course.", 400)
                    db.execute("INSERT INTO employee_courses (employee_id, course_id) VALUES (%s, %s)", (employee_pk, course_id))
            db.connection.commit()
        return jsonify(message="Employee updated.")
    except ValueError as error:
        return json_error(str(error), 400)
    except Exception as error:
        return _commit_error(error)


@bp.post("/employees/<int:employee_pk>/reset-password")
@require_role("admin")
@require_csrf
def reset_employee_password(employee_pk):
    password = generate_memorable_password()
    with cursor() as db:
        db.execute("SELECT user_id FROM employees WHERE id = %s", (employee_pk,))
        employee = db.fetchone()
        if not employee:
            return json_error("Employee not found.", 404)
        db.execute(
            """UPDATE users SET password_hash = %s, auth_version = auth_version + 1,
                      must_change_password = TRUE WHERE id = %s""",
            (hash_password(password), employee["user_id"]),
        )
        db.connection.commit()
    return jsonify(temporary_password=password)


@bp.delete("/employees/<int:employee_pk>")
@require_role("admin")
@require_csrf
def delete_employee(employee_pk):
    connection = None
    try:
        if _payload().get("confirmation") != "DELETE":
            return json_error("Type DELETE to permanently remove this employee account.", 400)
        with cursor() as db:
            db.connection.start_transaction()
            connection = db.connection
            db.execute("SELECT user_id FROM employees WHERE id = %s", (employee_pk,))
            employee = db.fetchone()
            if not employee:
                db.connection.rollback()
                return json_error("Employee not found.", 404)
            db.execute(
                "DELETE FROM employees WHERE id = %s",
                (employee_pk,),
            )
            db.execute(
                "DELETE FROM users WHERE id = %s",
                (employee["user_id"],),
            )
            db.connection.commit()
        return jsonify(message="Employee account permanently deleted.")
    except ValueError as error:
        return json_error(str(error), 400)
    except Exception as error:
        if connection is not None:
            connection.rollback()
        return _commit_error(error)


@bp.get("/courses")
@require_role("admin")
def courses():
    with cursor() as db:
        db.execute("SELECT * FROM courses ORDER BY name")
        return jsonify(courses=db.fetchall())


@bp.post("/courses")
@require_role("admin")
@require_csrf
def create_course():
    try:
        data = _payload()
        code = validated_text(data, "course_code", max_length=40)
        name = validated_text(data, "name", max_length=180)
        fee = Decimal(str(data.get("fee", "0")))
        if not fee.is_finite() or fee < 0 or fee > Decimal("99999999.99"):
            return json_error("Fee must be a valid non-negative amount.", 400)
        duration = data.get("duration_months")
        if duration is not None and (not isinstance(duration, int) or duration < 1 or duration > 600):
            return json_error("Duration must be a positive number of months.", 400)
        status = data.get("status", "active")
        if status not in ("active", "inactive"):
            return json_error("Status must be active or inactive.", 400)
        with cursor() as db:
            db.execute(
                """INSERT INTO courses (course_code, name, description, duration_months, fee, status)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    code, name, validated_text(data, "description", required=False, max_length=5000),
                    duration, fee, status,
                ),
            )
            db.connection.commit()
            course_id = db.lastrowid
        return jsonify(course_id=course_id), 201
    except (ValueError, InvalidOperation):
        return json_error("Course details are invalid.", 400)
    except IntegrityError:
        return json_error("Course code already exists.", 409)
    except Exception as error:
        return _commit_error(error)


@bp.put("/courses/<int:course_id>")
@require_role("admin")
@require_csrf
def update_course(course_id):
    try:
        data = _payload()
        allowed = {"course_code": 40, "name": 180, "description": 5000}
        updates = {field: validated_text(data, field, max_length=limit)
                   for field, limit in allowed.items() if field in data}
        if "fee" in data:
            fee = Decimal(str(data["fee"]))
            if not fee.is_finite() or fee < 0 or fee > Decimal("99999999.99"):
                return json_error("Fee must be a valid non-negative amount.", 400)
            updates["fee"] = fee
        if "duration_months" in data:
            duration = data["duration_months"]
            if duration is not None and (not isinstance(duration, int) or duration < 1 or duration > 600):
                return json_error("Duration must be a positive number of months.", 400)
            updates["duration_months"] = duration
        if "status" in data:
            if data["status"] not in ("active", "inactive"):
                return json_error("Status must be active or inactive.", 400)
            updates["status"] = data["status"]
        if not updates:
            return json_error("No course fields were provided.", 400)
        with cursor() as db:
            db.execute("SELECT id FROM courses WHERE id = %s", (course_id,))
            if not db.fetchone():
                return json_error("Course not found.", 404)
            assignments = ", ".join(f"{field} = %s" for field in updates)
            db.execute(f"UPDATE courses SET {assignments} WHERE id = %s", (*updates.values(), course_id))
            db.connection.commit()
        return jsonify(message="Course updated.")
    except (ValueError, InvalidOperation):
        return json_error("Course details are invalid.", 400)
    except IntegrityError:
        return json_error("Course code already exists.", 409)
    except Exception as error:
        return _commit_error(error)


STUDENT_STATUSES = ("present", "absent", "late", "leave")
EMPLOYEE_STATUSES = ("present", "absent", "late", "leave", "half_day")
ALL_STATUSES = tuple(sorted(set(STUDENT_STATUSES) | set(EMPLOYEE_STATUSES)))


def _person_type():
    person_type = request.args.get("person_type", "student").strip().lower() or "student"
    if person_type not in ("student", "employee"):
        return None
    return person_type


def _positive_int(raw):
    value = int(raw)
    if value < 1:
        raise ValueError
    return value


@bp.get("/attendance")
@require_role("admin")
def list_attendance():
    """Attendance history for both students and employees."""
    person_type = _person_type()
    if person_type is None:
        return json_error("Person type must be student or employee.", 400)
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    try:
        course_id = request.args.get("course_id", "").strip()
        course_id = _positive_int(course_id) if course_id else None
        person_value = request.args.get("person_id", "").strip()
        person_id = _positive_int(person_value) if person_value else None
        date_from = date.fromisoformat(date_from) if date_from else None
        date_to = date.fromisoformat(date_to) if date_to else None
    except ValueError:
        return json_error("Attendance filters are invalid.", 400)
    status = request.args.get("status", "").strip()
    if status and status not in ALL_STATUSES:
        return json_error("Attendance status filter is invalid.", 400)
    search = request.args.get("search", "").strip()[:100]

    if person_type == "student":
        conditions, params = [], []
        if course_id is not None:
            conditions.append("a.course_id = %s")
            params.append(course_id)
        if person_id is not None:
            conditions.append("a.student_id = %s")
            params.append(person_id)
        if date_from:
            conditions.append("a.attendance_date >= %s")
            params.append(date_from)
        if date_to:
            conditions.append("a.attendance_date <= %s")
            params.append(date_to)
        if status:
            conditions.append("a.status = %s")
            params.append(status)
        if search:
            conditions.append("(s.student_id LIKE %s OR s.full_name LIKE %s OR s.email LIKE %s OR s.phone LIKE %s)")
            params.extend((f"%{search}%",) * 4)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with cursor() as db:
            db.execute(
                f"""SELECT a.id, a.attendance_date, a.status, a.remarks,
                           a.course_id, a.student_id AS person_id,
                           s.student_id, s.full_name, s.email, s.phone,
                           c.name AS course_name, e.full_name AS employee_name
                    FROM attendance a
                    JOIN students s ON s.id = a.student_id
                    JOIN courses c ON c.id = a.course_id
                    LEFT JOIN employees e ON e.id = a.employee_id
                    {where}
                    ORDER BY a.attendance_date DESC, s.full_name LIMIT 500""",
                tuple(params),
            )
            rows = db.fetchall()
        for row in rows:
            row["person_type"] = "student"
            row["attendance_date"] = str(row["attendance_date"])
        return jsonify(attendance=rows, person_type="student")

    conditions, params = [], []
    if person_id is not None:
        conditions.append("ea.employee_id = %s")
        params.append(person_id)
    if date_from:
        conditions.append("ea.attendance_date >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("ea.attendance_date <= %s")
        params.append(date_to)
    if status:
        conditions.append("ea.status = %s")
        params.append(status)
    if search:
        conditions.append("(e.employee_id LIKE %s OR e.full_name LIKE %s OR e.email LIKE %s OR e.phone LIKE %s OR e.designation LIKE %s)")
        params.extend((f"%{search}%",) * 5)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with cursor() as db:
        db.execute(
            f"""SELECT ea.id, ea.attendance_date, ea.status, ea.remarks,
                       ea.employee_id AS person_id,
                       e.employee_id, e.full_name, e.email, e.phone, e.designation,
                       NULL AS student_id, NULL AS course_id, NULL AS course_name,
                       NULL AS employee_name
                FROM employee_attendance ea
                JOIN employees e ON e.id = ea.employee_id
                {where}
                ORDER BY ea.attendance_date DESC, e.full_name LIMIT 500""",
            tuple(params),
        )
        rows = db.fetchall()
    for row in rows:
        row["person_type"] = "employee"
        row["attendance_date"] = str(row["attendance_date"])
    return jsonify(attendance=rows, person_type="employee")


@bp.get("/attendance/lookup")
@require_role("admin")
def lookup_attendance():
    """Return the record for one person/course/date so the form can load it.

    This is what lets the UI switch from "Save" to "Update" instead of hitting a
    duplicate-key dead end.
    """
    try:
        person_type = _person_type()
        if person_type is None:
            return json_error("Person type must be student or employee.", 400)
        person_value = request.args.get("person_id", "").strip()
        person_id = _positive_int(person_value) if person_value else None
        course_value = request.args.get("course_id", "").strip()
        course_id = _positive_int(course_value) if course_value else None
        attendance_date = date.fromisoformat(request.args.get("date", "").strip())
    except ValueError:
        return json_error("Attendance lookup parameters are invalid.", 400)
    if person_id is None:
        return json_error("A person is required.", 400)
    if person_type == "student" and course_id is None:
        return json_error("A course is required for student attendance.", 400)

    with cursor() as db:
        if person_type == "student":
            db.execute(
                """SELECT a.id, a.status, a.remarks, a.attendance_date, a.course_id,
                          a.student_id AS person_id, 'student' AS person_type
                   FROM attendance a
                   WHERE a.student_id = %s AND a.course_id = %s AND a.attendance_date = %s
                   LIMIT 1""",
                (person_id, course_id, attendance_date),
            )
        else:
            db.execute(
                """SELECT ea.id, ea.status, ea.remarks, ea.attendance_date, NULL AS course_id,
                          ea.employee_id AS person_id, 'employee' AS person_type
                   FROM employee_attendance ea
                   WHERE ea.employee_id = %s AND ea.attendance_date = %s LIMIT 1""",
                (person_id, attendance_date),
            )
        record = db.fetchone()
    if not record:
        return jsonify(found=False, mode="create", person_type=person_type)
    record["attendance_date"] = str(record["attendance_date"])
    return jsonify(found=True, mode="update", record=record, person_type=person_type)


def _attendance_payload(data, person_type):
    try:
        person_value = data.get("person_id")
        course_value = data.get("course_id")
        person_id = int(person_value)
        if person_id < 1:
            raise ValueError
        course_id = None
        if course_value not in (None, ""):
            course_id = int(course_value)
            if course_id < 1:
                raise ValueError
        attendance_date = _optional_date(data, "date") or date.today()
        remarks = validated_text(data, "remarks", required=False, max_length=500)
    except (TypeError, ValueError) as error:
        return None, None, json_error(str(error) or "Attendance details are invalid.", 400)

    allowed = EMPLOYEE_STATUSES if person_type == "employee" else STUDENT_STATUSES
    status = data.get("status")
    if status not in allowed:
        return None, None, json_error("Attendance status is invalid.", 400)
    if person_type == "student" and course_id is None:
        return None, None, json_error("A course is required for student attendance.", 400)
    return (person_id, course_id, attendance_date, status, remarks), allowed, None


@bp.post("/attendance")
@require_role("admin")
@require_csrf
def create_attendance():
    """Create or update attendance for a person on a date.

    The unique key is (student, course, date) for students and (employee, date)
    for employees. A save that collides with an existing row updates that row
    instead of failing, which is the behaviour the admin UI depends on.
    """
    person_type = (request.get_json(silent=True) or {}).get("person_type", "student")
    if person_type not in ("student", "employee"):
        return json_error("Person type must be student or employee.", 400)
    try:
        data = _payload()
    except ValueError as error:
        return json_error(str(error), 400)
    parsed, _allowed, error = _attendance_payload(data, person_type)
    if error:
        return error
    person_id, course_id, attendance_date, status, remarks = parsed

    try:
        with cursor() as db:
            connection = db.connection
            connection.start_transaction()
            if person_type == "student":
                db.execute(
                    "SELECT sc.employee_id FROM student_courses sc "
                    "WHERE sc.student_id = %s AND sc.course_id = %s",
                    (person_id, course_id),
                )
                enrollment = db.fetchone()
                if not enrollment:
                    connection.rollback()
                    return json_error("Student is not enrolled in this course.", 400)
                db.execute(
                    """INSERT INTO attendance
                       (student_id, employee_id, course_id, attendance_date, status, remarks)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                         employee_id = VALUES(employee_id),
                         status = VALUES(status),
                         remarks = VALUES(remarks),
                         id = LAST_INSERT_ID(id)""",
                    (person_id, enrollment["employee_id"], course_id, attendance_date, status, remarks),
                )
                attendance_id = db.lastrowid
            else:
                db.execute("SELECT id FROM employees WHERE id = %s", (person_id,))
                if not db.fetchone():
                    connection.rollback()
                    return json_error("Employee not found.", 404)
                db.execute(
                    """INSERT INTO employee_attendance
                       (employee_id, attendance_date, status, remarks)
                       VALUES (%s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                         status = VALUES(status),
                         remarks = VALUES(remarks),
                         id = LAST_INSERT_ID(id)""",
                    (person_id, attendance_date, status, remarks),
                )
                attendance_id = db.lastrowid
            connection.commit()
    except IntegrityError as error:
        current_app.logger.exception("Attendance save conflicted", exc_info=error)
        return json_error(
            "Attendance for this person and date already exists and could not be updated. "
            "The existing record has been loaded so you can review it.",
            409,
        )
    except Exception as error:
        return _commit_error(error)
    return jsonify(
        attendance_id=attendance_id,
        person_type=person_type,
        message="Attendance saved successfully.",
    ), 201


@bp.put("/attendance/<int:attendance_id>")
@require_role("admin")
@require_csrf
def update_attendance(attendance_id):
    try:
        data = _payload()
    except ValueError as error:
        return json_error(str(error), 400)
    person_type = data.get("person_type", "student")
    if person_type not in ("student", "employee"):
        return json_error("Person type must be student or employee.", 400)
    parsed, _allowed, error = _attendance_payload(data, person_type)
    if error:
        return error
    person_id, course_id, attendance_date, status, remarks = parsed

    try:
        with cursor() as db:
            connection = db.connection
            connection.start_transaction()
            if person_type == "student":
                db.execute(
                    "SELECT id FROM attendance WHERE id = %s", (attendance_id,),
                )
                if not db.fetchone():
                    connection.rollback()
                    return json_error("Attendance record not found.", 404)
                db.execute(
                    """UPDATE attendance
                       SET student_id = %s, course_id = %s, attendance_date = %s,
                           status = %s, remarks = %s
                       WHERE id = %s""",
                    (person_id, course_id, attendance_date, status, remarks, attendance_id),
                )
            else:
                db.execute(
                    "SELECT id FROM employee_attendance WHERE id = %s", (attendance_id,),
                )
                if not db.fetchone():
                    connection.rollback()
                    return json_error("Attendance record not found.", 404)
                db.execute(
                    """UPDATE employee_attendance
                       SET employee_id = %s, attendance_date = %s, status = %s, remarks = %s
                       WHERE id = %s""",
                    (person_id, attendance_date, status, remarks, attendance_id),
                )
            connection.commit()
    except IntegrityError as error:
        current_app.logger.exception("Attendance update conflicted", exc_info=error)
        return json_error(
            "Attendance already exists for this person and date. "
            "The existing record has been loaded so you can update it.",
            409,
        )
    except Exception as error:
        return _commit_error(error)
    return jsonify(message="Attendance updated.")


@bp.delete("/attendance/<int:attendance_id>")
@require_role("admin")
@require_csrf
def delete_attendance(attendance_id):
    person_type = (request.get_json(silent=True) or {}).get("person_type", "student")
    table = "employee_attendance" if person_type == "employee" else "attendance"
    connection = None
    try:
        with cursor() as db:
            connection = db.connection
            connection.start_transaction()
            db.execute(f"DELETE FROM {table} WHERE id = %s", (attendance_id,))
            if db.rowcount == 0:
                connection.rollback()
                return json_error("Attendance record not found.", 404)
            connection.commit()
    except Exception as error:
        if connection is not None:
            connection.rollback()
        return _commit_error(error)
    return jsonify(message="Attendance deleted.")


@bp.get("/attendance/report")
@require_role("admin")
def attendance_report():
    """Present / absent / leave / late totals and percentage for one person."""
    person_type = _person_type()
    if person_type is None:
        return json_error("Person type must be student or employee.", 400)
    try:
        person_id = _positive_int(request.args.get("person_id", "").strip())
    except ValueError:
        return json_error("A valid person is required.", 400)
    course_value = request.args.get("course_id", "").strip()
    try:
        course_id = _positive_int(course_value) if course_value else None
    except ValueError:
        return json_error("Course filter is invalid.", 400)

    with cursor() as db:
        if person_type == "student":
            db.execute(
                "SELECT student_id, student_id AS code, full_name FROM students WHERE id = %s",
                (person_id,),
            )
        else:
            db.execute(
                "SELECT employee_id, employee_id AS code, full_name FROM employees WHERE id = %s",
                (person_id,),
            )
        person = db.fetchone()
        if not person:
            return json_error("Person not found.", 404)
        if person_type == "student":
            conditions, params = ["a.student_id = %s"], [person_id]
            if course_id is not None:
                conditions.append("a.course_id = %s")
                params.append(course_id)
            db.execute(
                f"""SELECT COUNT(*) AS total,
                           SUM(a.status = 'present') AS present,
                           SUM(a.status = 'absent')  AS absent,
                           SUM(a.status = 'leave')   AS on_leave,
                           SUM(a.status = 'late')    AS late,
                           SUM(a.status = 'half_day') AS half_day
                    FROM attendance a WHERE {' AND '.join(conditions)}""",
                tuple(params),
            )
        else:
            db.execute(
                """SELECT COUNT(*) AS total,
                          SUM(status = 'present') AS present,
                          SUM(status = 'absent')  AS absent,
                          SUM(status = 'leave')   AS on_leave,
                          SUM(status = 'late')    AS late,
                          SUM(status = 'half_day') AS half_day
                   FROM employee_attendance WHERE employee_id = %s""",
                (person_id,),
            )
        totals = db.fetchone()

    # SUM() over a boolean comes back as Decimal; a half day counts as attending,
    # but only half of the time.
    total = int(totals["total"] or 0)
    present = int(totals["present"] or 0)
    half_day = int(totals["half_day"] or 0)
    attended = present + half_day / 2
    percentage = round(attended * 100 / total, 2) if total else 0.0
    report = {
        "person_type": person_type,
        "code": person["code"],
        "full_name": person["full_name"],
        "total": total,
        "present": present,
        "absent": int(totals["absent"] or 0),
        "leave": int(totals["on_leave"] or 0),
        "late": int(totals["late"] or 0),
        "half_day": half_day,
        "percentage": percentage,
    }
    return jsonify(report=report)


ASSIGNMENT_STATUSES = ("active", "draft", "closed")


def _assignment_payload(data):
    """Validate an assignment. The course link is the part that must be right:
    student and employee visibility both filter on assignments.course_id.
    """
    title = validated_text(data, "title", max_length=200)
    description = validated_text(data, "description", required=False, max_length=10000)
    resource_url = validated_text(data, "resource_url", required=False, max_length=500)
    course_id = data.get("course_id")
    if not isinstance(course_id, int) or isinstance(course_id, bool) or course_id < 1:
        raise ValueError("A valid course is required.")
    due_date = _optional_date(data, "due_date")
    status = data.get("status", "active")
    if status not in ASSIGNMENT_STATUSES:
        raise ValueError("Assignment status is invalid.")
    if resource_url and not re.fullmatch(r"https?://[^\s]+", resource_url):
        raise ValueError("Resource URL must start with http:// or https://")
    return {
        "title": title,
        "description": description,
        "course_id": course_id,
        "due_date": due_date,
        "resource_url": resource_url,
        "status": status,
    }


@bp.get("/assignments")
@require_role("admin")
def list_assignments():
    course_value = request.args.get("course_id", "").strip()
    try:
        course_id = int(course_value) if course_value else None
        if course_id is not None and course_id < 1:
            raise ValueError
    except ValueError:
        return json_error("Course filter is invalid.", 400)
    status = request.args.get("status", "").strip()
    if status and status not in ASSIGNMENT_STATUSES:
        return json_error("Assignment status filter is invalid.", 400)
    search = request.args.get("search", "").strip()[:100]
    conditions, params = [], []
    if course_id is not None:
        conditions.append("a.course_id = %s")
        params.append(course_id)
    if status:
        conditions.append("a.status = %s")
        params.append(status)
    if search:
        conditions.append("(a.title LIKE %s OR c.name LIKE %s)")
        params.extend((f"%{search}%", f"%{search}%"))
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with cursor() as db:
        db.execute(
            f"""SELECT a.id, a.title, a.description, a.due_date, a.status, a.course_id,
                       a.created_by, a.created_at, a.attachment AS resource_url,
                       c.name AS course_name, COALESCE(u.login_id, 'Admin') AS created_by_login
                FROM assignments a
                JOIN courses c ON c.id = a.course_id
                LEFT JOIN users u ON u.id = a.created_by
                {where}
                ORDER BY a.created_at DESC LIMIT 500""",
            tuple(params),
        )
        rows = db.fetchall()
    for row in rows:
        row["due_date"] = str(row["due_date"]) if row["due_date"] else None
    return jsonify(assignments=rows)


@bp.post("/assignments")
@require_role("admin")
@require_csrf
def create_assignment():
    try:
        data = _payload()
        fields = _assignment_payload(data)
    except ValueError as error:
        return json_error(str(error), 400)
    with cursor() as db:
        db.execute("SELECT id FROM courses WHERE id = %s", (fields["course_id"],))
        if not db.fetchone():
            return json_error("Course not found.", 404)
        db.execute(
            """INSERT INTO assignments
               (title, description, course_id, created_by, due_date, attachment, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                fields["title"], fields["description"], fields["course_id"],
                request.current_user["id"], fields["due_date"],
                fields["resource_url"], fields["status"],
            ),
        )
        db.connection.commit()
        assignment_id = db.lastrowid
    return jsonify(assignment_id=assignment_id, message="Assignment created successfully."), 201


@bp.put("/assignments/<int:assignment_id>")
@require_role("admin")
@require_csrf
def update_assignment(assignment_id):
    try:
        data = _payload()
        fields = _assignment_payload(data)
    except ValueError as error:
        return json_error(str(error), 400)
    with cursor() as db:
        db.execute("SELECT id FROM assignments WHERE id = %s", (assignment_id,))
        if not db.fetchone():
            return json_error("Assignment not found.", 404)
        db.execute("SELECT id FROM courses WHERE id = %s", (fields["course_id"],))
        if not db.fetchone():
            return json_error("Course not found.", 404)
        db.execute(
            """UPDATE assignments
               SET title = %s, description = %s, course_id = %s, due_date = %s,
                   attachment = %s, status = %s
               WHERE id = %s""",
            (
                fields["title"], fields["description"], fields["course_id"],
                fields["due_date"], fields["resource_url"], fields["status"],
                assignment_id,
            ),
        )
        db.connection.commit()
    return jsonify(message="Assignment updated.")


@bp.delete("/assignments/<int:assignment_id>")
@require_role("admin")
@require_csrf
def delete_assignment(assignment_id):
    connection = None
    try:
        with cursor() as db:
            connection = db.connection
            connection.start_transaction()
            db.execute("DELETE FROM assignments WHERE id = %s", (assignment_id,))
            if db.rowcount == 0:
                connection.rollback()
                return json_error("Assignment not found.", 404)
            connection.commit()
    except Exception as error:
        if connection is not None:
            connection.rollback()
        return _commit_error(error)
    return jsonify(message="Assignment deleted.")


@bp.get("/materials")
@require_role("admin")
def list_materials():
    with cursor() as db:
        db.execute(
            """SELECT m.id, m.title, m.description, m.file_url, m.created_at,
                      c.name AS course_name
               FROM study_materials m JOIN courses c ON c.id = m.course_id
               ORDER BY m.created_at DESC LIMIT 500"""
        )
        return jsonify(materials=db.fetchall())


@bp.get("/fees")
@require_role("admin")
def list_fees():
    with cursor() as db:
        db.execute(
            """SELECT f.id, s.student_id, s.full_name, c.name AS course_name,
                      f.amount, f.paid_amount, f.due_amount, f.payment_date,
                      f.payment_status, f.remarks
               FROM fees f JOIN students s ON s.id = f.student_id
               LEFT JOIN courses c ON c.id = f.course_id
               ORDER BY f.created_at DESC LIMIT 500"""
        )
        return jsonify(fees=db.fetchall())


@bp.get("/announcements")
@require_role("admin")
def list_announcements():
    with cursor() as db:
        db.execute(
            """SELECT a.id, a.title, a.body, a.audience, a.published_at,
                      c.name AS course_name
               FROM announcements a LEFT JOIN courses c ON c.id = a.course_id
               ORDER BY a.published_at DESC LIMIT 500"""
        )
        return jsonify(announcements=db.fetchall())


@bp.post("/announcements")
@require_role("admin")
@require_csrf
def create_announcement():
    try:
        data = _payload()
        title = validated_text(data, "title", max_length=180)
        body = validated_text(data, "body", max_length=5000)
        audience = data.get("audience", "all")
        course_id = data.get("course_id")
        if audience not in ("all", "student", "employee"):
            return json_error("Announcement audience is invalid.", 400)
        if course_id is not None and (not isinstance(course_id, int) or course_id < 1):
            return json_error("Course assignment is invalid.", 400)
        with cursor() as db:
            if course_id is not None:
                db.execute("SELECT id FROM courses WHERE id = %s AND status = 'active'", (course_id,))
                if not db.fetchone():
                    return json_error("Course not found or inactive.", 404)
            db.execute(
                """INSERT INTO announcements
                   (title, body, audience, course_id, created_by)
                   VALUES (%s, %s, %s, %s, %s)""",
                (title, body, audience, course_id, request.current_user["id"]),
            )
            announcement_id = db.lastrowid
            db.connection.commit()
        return jsonify(announcement_id=announcement_id), 201
    except ValueError as error:
        return json_error(str(error), 400)
    except Exception as error:
        return _commit_error(error)


@bp.post("/fees")
@require_role("admin")
@require_csrf
def create_fee():
    try:
        data = _payload()
        student_pk = data.get("student_id")
        course_id = data.get("course_id")
        amount = Decimal(str(data.get("amount")))
        paid = Decimal(str(data.get("paid_amount", 0)))
        payment_date = _optional_date(data, "payment_date")
        remarks = validated_text(data, "remarks", required=False, max_length=500)
    except (ValueError, InvalidOperation):
        return json_error("Fee details are invalid.", 400)
    if not isinstance(student_pk, int) or student_pk < 1:
        return json_error("A valid student is required.", 400)
    if course_id is not None and (not isinstance(course_id, int) or course_id < 1):
        return json_error("Course is invalid.", 400)
    if (
        not amount.is_finite() or not paid.is_finite() or amount <= 0
        or amount > Decimal("99999999.99") or paid < 0 or paid > amount
    ):
        return json_error("Paid amount must be between zero and the total fee.", 400)
    due = amount - paid
    payment_status = "paid" if due == 0 else ("partial" if paid else "pending")
    with cursor() as db:
        db.execute("SELECT id FROM students WHERE id = %s", (student_pk,))
        if not db.fetchone():
            return json_error("Student not found.", 404)
        if course_id is not None:
            db.execute(
                "SELECT id FROM student_courses WHERE student_id = %s AND course_id = %s",
                (student_pk, course_id),
            )
            if not db.fetchone():
                return json_error("Student is not enrolled in this course.", 400)
        db.execute(
            """INSERT INTO fees
               (student_id, course_id, amount, paid_amount, due_amount, payment_date, payment_status, remarks)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (student_pk, course_id, amount, paid, due, payment_date, payment_status, remarks),
        )
        db.connection.commit()
        fee_id = db.lastrowid
    return jsonify(fee_id=fee_id), 201


@bp.get("/results")
@require_role("admin")
def list_results():
    with cursor() as db:
        db.execute(
            """SELECT r.*, s.student_id AS student_number, s.full_name, c.name AS course_name
               FROM results r JOIN students s ON s.id = r.student_id
               JOIN courses c ON c.id = r.course_id ORDER BY r.exam_date DESC LIMIT 500"""
        )
        return jsonify(results=db.fetchall())


@bp.post("/results")
@require_role("admin")
@require_csrf
def create_result():
    try:
        data = _payload()
        student_pk = data.get("student_id")
        course_id = data.get("course_id")
        subject = validated_text(data, "subject", max_length=150)
        grade = validated_text(data, "grade", required=False, max_length=20)
        exam_date = _optional_date(data, "exam_date")
        marks = Decimal(str(data.get("marks")))
    except (ValueError, InvalidOperation):
        return json_error("Result details are invalid.", 400)
    if not isinstance(student_pk, int) or student_pk < 1 or not isinstance(course_id, int) or course_id < 1:
        return json_error("Student and course are required.", 400)
    if not marks.is_finite() or marks < 0 or marks > 100000:
        return json_error("Marks must be a valid non-negative number.", 400)
    with cursor() as db:
        db.execute(
            "SELECT id FROM student_courses WHERE student_id = %s AND course_id = %s",
            (student_pk, course_id),
        )
        if not db.fetchone():
            return json_error("Student is not enrolled in this course.", 400)
        db.execute(
            "INSERT INTO results (student_id, course_id, subject, marks, grade, exam_date) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (student_pk, course_id, subject, marks, grade, exam_date),
        )
        db.connection.commit()
        result_id = db.lastrowid
    return jsonify(result_id=result_id), 201
