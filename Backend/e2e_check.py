"""End-to-end verification against the real MySQL database.

Creates a temporary admin, a student, an employee and a second student in a
different course, then exercises the exact flows from the task: attendance
create -> update (no duplicate), employee attendance, assignment visibility for
the right student/employee and not for others, and the search endpoints.
Everything it creates is removed at the end.
"""
import os
import sys
from datetime import date, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("SECRET_KEY", "e2e-only-secret-key")

from dotenv import load_dotenv

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from Backend.app import create_app
from Backend.db import cursor
from Backend.utils import hash_password

PASS = "Verify12345"
ADMIN_LOGIN = "ADME2E001"
STUDENT_LOGIN = "DME2E0001"
OTHER_STUDENT_LOGIN = "DME2E0002"
EMPLOYEE_LOGIN = "EMPE2E001"
MARKER = "E2E"
FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label} -> {detail}")
        FAILURES.append(label)


def seed():
    today = date.today()
    with cursor() as db:
        db.execute("SELECT id, name FROM courses ORDER BY id LIMIT 1")
        course = db.fetchone()
        course_id = course["id"]
        db.execute("SELECT id FROM courses WHERE id != %s ORDER BY id LIMIT 1", (course_id,))
        other_course_id = db.fetchone()["id"]

        ids = {}

        db.execute(
            """INSERT INTO users (login_id, password_hash, role, status, must_change_password)
               VALUES (%s, %s, 'admin', 'active', FALSE)""",
            (ADMIN_LOGIN, hash_password(PASS)),
        )
        admin_user_id = db.lastrowid
        db.execute("INSERT INTO admins (user_id, full_name) VALUES (%s, 'E2E Admin')", (admin_user_id,))
        ids["admin"] = admin_user_id

        for key, login_id, name, phone, email in (
            ("student", STUDENT_LOGIN, "Rahul E2E Sharma", "9876500001", "rahul.e2e@example.com"),
            ("other_student", OTHER_STUDENT_LOGIN, "Other E2E Student", "9876500003", "other.e2e@example.com"),
        ):
            db.execute(
                """INSERT INTO users (login_id, password_hash, role, status, must_change_password)
                   VALUES (%s, %s, 'student', 'active', FALSE)""",
                (login_id, hash_password(PASS)),
            )
            user_id = db.lastrowid
            db.execute(
                """INSERT INTO students (user_id, student_id, full_name, phone, email)
                   VALUES (%s, %s, %s, %s, %s)""",
                (user_id, login_id, name, phone, email),
            )
            ids[key] = db.lastrowid

        db.execute(
            """INSERT INTO users (login_id, password_hash, role, status, must_change_password)
               VALUES (%s, %s, 'employee', 'active', FALSE)""",
            (EMPLOYEE_LOGIN, hash_password(PASS)),
        )
        employee_user_id = db.lastrowid
        db.execute(
            """INSERT INTO employees (user_id, employee_id, full_name, phone, email, designation)
               VALUES (%s, %s, 'Amit E2E Sharma', '9876500002', 'amit.e2e@example.com', 'Senior Trainer')""",
            (employee_user_id, EMPLOYEE_LOGIN),
        )
        employee_id = db.lastrowid
        ids["employee"] = employee_id

        db.execute(
            "INSERT INTO student_courses (student_id, course_id, employee_id, status) VALUES (%s, %s, %s, 'active')",
            (ids["student"], course_id, employee_id),
        )
        db.execute(
            "INSERT INTO student_courses (student_id, course_id, employee_id, status) VALUES (%s, %s, NULL, 'active')",
            (ids["other_student"], other_course_id),
        )
        db.execute(
            "INSERT INTO employee_courses (employee_id, course_id) VALUES (%s, %s)",
            (employee_id, course_id),
        )
        db.connection.commit()

    print(f"  course={course_id} other_course={other_course_id} "
          f"student={ids['student']} other_student={ids['other_student']} employee={employee_id}")
    return ids, course_id, other_course_id


def cleanup():
    # assignments.created_by references users, so remove them before the accounts.
    with cursor() as db:
        db.execute("DELETE FROM assignments WHERE created_by IN "
                   "(SELECT id FROM users WHERE login_id IN (%s, %s, %s, %s))",
                   (ADMIN_LOGIN, STUDENT_LOGIN, OTHER_STUDENT_LOGIN, EMPLOYEE_LOGIN))
        db.execute("DELETE FROM assignments WHERE title LIKE '%E2E%'")
        db.execute("DELETE FROM students WHERE student_id IN (%s, %s)", (STUDENT_LOGIN, OTHER_STUDENT_LOGIN))
        db.execute("DELETE FROM employees WHERE employee_id = %s", (EMPLOYEE_LOGIN,))
        db.execute("DELETE FROM users WHERE login_id IN (%s, %s, %s, %s)",
                   (ADMIN_LOGIN, STUDENT_LOGIN, OTHER_STUDENT_LOGIN, EMPLOYEE_LOGIN))
        db.connection.commit()


def main():
    # The login limiter is 5/minute in production; this script signs in as several
    # roles, so raise it for the test app only. The limiter itself is still active.
    app = create_app({"LOGIN_RATE_LIMIT": "1000 per minute"})
    with app.app_context():
        return run_checks(app)


def run_checks(app):
    client = app.test_client()
    today = date.today()
    day_one = (today - timedelta(days=10)).isoformat()
    day_two = (today - timedelta(days=9)).isoformat()

    def login(identifier, role):
        with client.session_transaction() as session:
            session.clear()
        response = client.post("/api/auth/login", json={
            "identifier": identifier, "password": PASS, "role": role,
        })
        if response.status_code != 200:
            raise SystemExit(f"login failed for {identifier}: {response.get_json()}")
        return client.get("/api/auth/me").get_json()["csrf_token"]

    print("\n=== Seeding test records ===")
    ids, course_id, other_course_id = seed()
    student_id, other_student_id, employee_id = ids["student"], ids["other_student"], ids["employee"]

    try:
        print("\n=== TEST A - Student attendance create then update ===")
        csrf = login(ADMIN_LOGIN, "admin")

        created = client.post("/api/admin/attendance", json={
            "person_type": "student", "person_id": student_id, "course_id": course_id,
            "date": day_one, "status": "present",
        }, headers={"X-CSRF-Token": csrf})
        check("Admin creates student attendance", created.status_code == 201, created.get_json())

        # The exact scenario from the task: same person/course/date, now Absent.
        updated = client.post("/api/admin/attendance", json={
            "person_type": "student", "person_id": student_id, "course_id": course_id,
            "date": day_one, "status": "absent",
        }, headers={"X-CSRF-Token": csrf})
        check("Re-saving the same day succeeds (no dead-end error)", updated.status_code == 201, updated.get_json())

        with cursor() as db:
            db.execute(
                "SELECT COUNT(*) AS n, MAX(status) AS status FROM attendance "
                "WHERE student_id = %s AND course_id = %s AND attendance_date = %s",
                (student_id, course_id, day_one),
            )
            row = db.fetchone()
        check("Exactly one record exists (no duplicate)", row["n"] == 1, row)
        check("Status updated to absent", row["status"] == "absent", row)

        lookup = client.get(
            f"/api/admin/attendance/lookup?person_type=student&person_id={student_id}"
            f"&course_id={course_id}&date={day_one}").get_json()
        check("Lookup reports update mode with existing status",
              lookup.get("mode") == "update" and lookup["record"]["status"] == "absent", lookup)

        print("\n=== TEST B - Employee attendance ===")
        emp_created = client.post("/api/admin/attendance", json={
            "person_type": "employee", "person_id": employee_id, "date": day_one, "status": "present",
        }, headers={"X-CSRF-Token": csrf})
        check("Admin creates employee attendance (no course)", emp_created.status_code == 201, emp_created.get_json())

        emp_updated = client.post("/api/admin/attendance", json={
            "person_type": "employee", "person_id": employee_id, "date": day_one, "status": "late",
        }, headers={"X-CSRF-Token": csrf})
        check("Employee attendance updates on re-save", emp_updated.status_code == 201, emp_updated.get_json())

        with cursor() as db:
            db.execute(
                "SELECT COUNT(*) AS n, MAX(status) AS status FROM employee_attendance "
                "WHERE employee_id = %s AND attendance_date = %s", (employee_id, day_one))
            row = db.fetchone()
        check("One employee record, status updated", row["n"] == 1 and row["status"] == "late", row)

        history = client.get("/api/admin/attendance?person_type=employee&search=EMPE2E001").get_json()
        check("Employee attendance appears in history", len(history["attendance"]) == 1, history)

        report = client.get(f"/api/admin/attendance/report?person_type=employee&person_id={employee_id}").get_json()
        check("Employee report has totals and percentage", report["report"]["total"] == 1, report)

        print("\n=== TEST C - Assignment visibility ===")
        made = client.post("/api/admin/assignments", json={
            "title": "E2E HTML Portfolio", "description": "Build a responsive portfolio.",
            "course_id": course_id, "due_date": (today + timedelta(days=7)).isoformat(), "status": "active",
        }, headers={"X-CSRF-Token": csrf})
        check("Admin creates assignment", made.status_code == 201, made.get_json())
        assignment_id = made.get_json()["assignment_id"]

        other = client.post("/api/admin/assignments", json={
            "title": "E2E Other Course Task", "course_id": other_course_id, "status": "active",
        }, headers={"X-CSRF-Token": csrf})
        check("Admin creates assignment for another course", other.status_code == 201, other.get_json())

        student_csrf = login(STUDENT_LOGIN, "student")
        titles = [i["title"] for i in client.get("/api/portal/assignments").get_json()["assignments"]]
        check("Student sees the course assignment", "E2E HTML Portfolio" in titles, titles)
        check("Student does NOT see the other course's assignment", "E2E Other Course Task" not in titles, titles)

        student_attendance = client.get("/api/portal/attendance").get_json()["attendance"]
        check("Student sees own attendance", len(student_attendance) >= 1, student_attendance)

        login(OTHER_STUDENT_LOGIN, "student")
        other_titles = [i["title"] for i in client.get("/api/portal/assignments").get_json()["assignments"]]
        check("Unauthorised student does NOT see the assignment", "E2E HTML Portfolio" not in other_titles, other_titles)

        employee_csrf = login(EMPLOYEE_LOGIN, "employee")
        employee_titles = [i["title"] for i in client.get("/api/portal/assignments").get_json()["assignments"]]
        check("Employee sees the admin-created assignment", "E2E HTML Portfolio" in employee_titles, employee_titles)
        check("Employee does NOT see the other course's assignment", "E2E Other Course Task" not in employee_titles, employee_titles)

        own = client.get("/api/portal/attendance").get_json()["attendance"]
        check("Employee sees own attendance record", len(own) == 1, own)

        blocked = client.post("/api/admin/attendance", json={
            "person_type": "student", "person_id": student_id, "course_id": course_id,
            "date": day_two, "status": "present",
        }, headers={"X-CSRF-Token": employee_csrf})
        check("Employee CANNOT manage attendance", blocked.status_code == 403, blocked.status_code)

        student_write = client.post("/api/admin/attendance", json={
            "person_type": "student", "person_id": student_id, "course_id": course_id,
            "date": day_two, "status": "present",
        }, headers={"X-CSRF-Token": student_csrf})
        check("Student CANNOT manage attendance", student_write.status_code == 403, student_write.status_code)

        print("\n=== TEST D - Search ===")
        csrf = login(ADMIN_LOGIN, "admin")

        for term, label in ((STUDENT_LOGIN, "student by ID"), ("Rahul", "student by name"),
                            ("rahul.e2e", "student by email"), ("9876500001", "student by phone")):
            result = client.get(f"/api/admin/search/students?q={term}").get_json()["students"]
            check(f"Search {label}", any(s["student_id"] == STUDENT_LOGIN for s in result), result)

        for term, label in ((EMPLOYEE_LOGIN, "employee by ID"), ("Amit", "employee by name"),
                            ("amit.e2e", "employee by email"), ("9876500002", "employee by phone"),
                            ("Senior Trainer", "employee by designation")):
            result = client.get(f"/api/admin/search/employees?q={term}").get_json()["employees"]
            check(f"Search {label}", any(e["employee_id"] == EMPLOYEE_LOGIN for e in result), result)

        limited = client.get("/api/admin/search/students?q=").get_json()["students"]
        check("Search is capped at a screenful", len(limited) <= 20, len(limited))

        scoped = client.get("/api/admin/search/students?q=Rahul")
        check("Admin student search authorised", scoped.status_code == 200, scoped.status_code)

        employee_csrf = login(EMPLOYEE_LOGIN, "employee")
        scoped = client.get("/api/admin/search/students?q=Rahul").get_json()["students"]
        check("Employee search is scoped to their own students",
              any(s["student_id"] == STUDENT_LOGIN for s in scoped), scoped)
        blocked = client.get("/api/admin/search/employees?q=Amit")
        check("Employee CANNOT search all employees", blocked.status_code == 403, blocked.status_code)

        student_blocked = None
        login(STUDENT_LOGIN, "student")
        student_blocked = client.get("/api/admin/search/students?q=Rahul")
        check("Student CANNOT use admin search", student_blocked.status_code == 403, student_blocked.status_code)

        print("\n=== TEST E - Assignment edit, draft visibility and delete ===")
        csrf = login(ADMIN_LOGIN, "admin")

        edited = client.put(f"/api/admin/assignments/{assignment_id}", json={
            "title": "E2E HTML Portfolio v2", "course_id": course_id,
            "due_date": (today + timedelta(days=9)).isoformat(), "status": "active",
        }, headers={"X-CSRF-Token": csrf})
        check("Admin edits assignment", edited.status_code == 200, edited.get_json())

        listed = client.get("/api/admin/assignments").get_json()["assignments"]
        check("Edited title persisted",
              any(a["id"] == assignment_id and a["title"] == "E2E HTML Portfolio v2" for a in listed))

        draft = client.post("/api/admin/assignments", json={
            "title": "E2E Hidden Draft", "course_id": course_id, "status": "draft",
        }, headers={"X-CSRF-Token": csrf})
        check("Admin creates a draft assignment", draft.status_code == 201, draft.get_json())

        login(STUDENT_LOGIN, "student")
        titles = [i["title"] for i in client.get("/api/portal/assignments").get_json()["assignments"]]
        check("Student sees the updated title", "E2E HTML Portfolio v2" in titles, titles)
        check("Student does NOT see draft assignments", "E2E Hidden Draft" not in titles, titles)

        # The checks above ended on a student session; the delete needs an admin.
        csrf = login(ADMIN_LOGIN, "admin")
        removed = client.delete(f"/api/admin/assignments/{assignment_id}", json={},
                                headers={"X-CSRF-Token": csrf})
        check("Admin deletes assignment", removed.status_code == 200, removed.get_json())

    finally:
        print("\n=== Cleanup ===")
        cleanup()
        print("  Test data removed.")

    print("\n" + "=" * 62)
    if FAILURES:
        print(f"RESULT: {len(FAILURES)} check(s) FAILED")
        for item in FAILURES:
            print(f"  - {item}")
        return 1
    print("RESULT: ALL END-TO-END CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())