import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("SECRET_KEY", "inspect")

from dotenv import load_dotenv

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from Backend.app import create_app
from Backend.db import cursor

app = create_app()
with app.app_context():
    with cursor() as db:
        db.execute("""SELECT a.id, s.student_id, c.name AS course, a.attendance_date, a.status, a.remarks
                      FROM attendance a JOIN students s ON s.id = a.student_id
                      JOIN courses c ON c.id = a.course_id ORDER BY a.id""")
        print("STUDENT ATTENDANCE ROWS:")
        for row in db.fetchall():
            print(" ", row)
        db.execute("""SELECT ea.id, e.employee_id, ea.attendance_date, ea.status
                      FROM employee_attendance ea JOIN employees e ON e.id = ea.employee_id ORDER BY ea.id""")
        print("EMPLOYEE ATTENDANCE ROWS:")
        for row in db.fetchall():
            print(" ", row)