"""Temporary QA data for the browser check. Removed by _qa_cleanup.py."""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("SECRET_KEY", "qa-only-secret-key")

from dotenv import load_dotenv

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from Backend.app import create_app
from Backend.db import cursor
from Backend.utils import hash_password

PASS = "QaVerify123"

app = create_app()
with app.app_context():
    with cursor() as db:
        db.execute("SELECT id FROM courses ORDER BY id LIMIT 1")
        course_id = db.fetchone()["id"]

        db.execute(
            """INSERT INTO users (login_id, password_hash, role, status, must_change_password)
               VALUES ('QAADMIN01', %s, 'admin', 'active', FALSE)""", (hash_password(PASS),))
        admin_user = db.lastrowid
        db.execute("INSERT INTO admins (user_id, full_name) VALUES (%s, 'QA Admin')", (admin_user,))

        db.execute(
            """INSERT INTO users (login_id, password_hash, role, status, must_change_password)
               VALUES ('QAEMP0001', %s, 'employee', 'active', FALSE)""", (hash_password(PASS),))
        employee_user = db.lastrowid
        db.execute(
            """INSERT INTO employees (user_id, employee_id, full_name, phone, email, designation)
               VALUES (%s, 'QAEMP0001', 'Rahul QA Sharma', '9811100001', 'rahul.qa@example.com', 'Senior Trainer')""",
            (employee_user,))
        employee_id = db.lastrowid

        db.execute(
            """INSERT INTO users (login_id, password_hash, role, status, must_change_password)
               VALUES ('QASTU0001', %s, 'student', 'active', FALSE)""", (hash_password(PASS),))
        student_user = db.lastrowid
        db.execute(
            """INSERT INTO students (user_id, student_id, full_name, phone, email)
               VALUES (%s, 'QASTU0001', 'Rahul QA Student', '9811100002', 'rahul.qa.stu@example.com')""",
            (student_user,))
        student_id = db.lastrowid

        db.execute(
            "INSERT INTO student_courses (student_id, course_id, employee_id, status) VALUES (%s, %s, %s, 'active')",
            (student_id, course_id, employee_id))
        # The browser test picks the course by typing "Advance Excel".
        db.execute("SELECT id FROM courses WHERE name LIKE '%%Excel%%' LIMIT 1")
        excel = db.fetchone()
        if excel:
            db.execute(
                "INSERT IGNORE INTO student_courses (student_id, course_id, employee_id, status) VALUES (%s, %s, %s, 'active')",
                (student_id, excel["id"], employee_id))
            course_id = excel["id"]
        db.execute("INSERT INTO employee_courses (employee_id, course_id) VALUES (%s, %s)",
                   (employee_id, course_id))
        db.connection.commit()

print(f"QA data ready. admin=QAADMIN01/{PASS} employee=QAEMP0001/{PASS} student=QASTU0001/{PASS}")