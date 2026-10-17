import os

from dotenv import load_dotenv

load_dotenv()
import mysql.connector as mysql_connector

connection = mysql_connector.connect(
    host=os.environ["DB_HOST"], port=int(os.environ["DB_PORT"]),
    database=os.environ["DB_NAME"], user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
)
cursor = connection.cursor()
cursor.execute("DELETE FROM assignments WHERE created_by IN (SELECT id FROM users WHERE login_id LIKE '%E2E%')")
print("assignments by e2e users:", cursor.rowcount)
cursor.execute("DELETE FROM assignments WHERE title LIKE '%E2E%'")
print("assignments by title:", cursor.rowcount)
cursor.execute("DELETE FROM students WHERE student_id LIKE '%E2E%'")
print("students:", cursor.rowcount)
cursor.execute("DELETE FROM employees WHERE employee_id LIKE '%E2E%'")
print("employees:", cursor.rowcount)
cursor.execute("DELETE FROM users WHERE login_id LIKE '%E2E%'")
print("users:", cursor.rowcount)
connection.commit()
for table in ("users", "students", "employees", "assignments", "attendance", "employee_attendance"):
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    print(f"{table}: {cursor.fetchone()[0]}")
connection.close()