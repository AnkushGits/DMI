import os
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("SECRET_KEY", "debug-secret")

from dotenv import load_dotenv

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from Backend.app import create_app
from Backend.db import cursor

app = create_app()
with app.app_context():
    with cursor() as db:
        db.execute("SELECT id, student_id FROM students WHERE student_id = 'QASTU0001'")
        student = db.fetchone()
        db.execute("SELECT sc.course_id FROM student_courses sc WHERE sc.student_id = %s AND sc.status='active'", (student["id"],))
        courses = db.fetchall()
        print("student:", student)
        print("enrolled courses:", courses)
        db.execute("SHOW COLUMNS FROM attendance")
        for column in db.fetchall():
            print(" ", column["Field"], column["Type"], "NULL" if column["Null"] == "YES" else "NOT NULL")

    try:
        with cursor() as db:
            db.connection.start_transaction()
            db.execute("SELECT sc.employee_id FROM student_courses sc WHERE sc.student_id = %s AND sc.course_id = %s",
                       (student["id"], courses[0]["course_id"]))
            enrollment = db.fetchone()
            print("enrollment:", enrollment)
            db.execute(
                """INSERT INTO attendance
                   (student_id, employee_id, course_id, attendance_date, status, remarks)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                     employee_id = VALUES(employee_id),
                     status = VALUES(status),
                     remarks = VALUES(remarks),
                     id = LAST_INSERT_ID(id)""",
                (student["id"], enrollment["employee_id"], courses[0]["course_id"], "2026-11-01", "present", None),
            )
            print("insert ok, lastrowid:", db.lastrowid)
            db.connection.commit()
    except Exception:
        traceback.print_exc()
    finally:
        with cursor() as db:
            db.execute("DELETE FROM attendance WHERE student_id = %s", (student["id"],))
            db.connection.commit()
            print("cleaned")