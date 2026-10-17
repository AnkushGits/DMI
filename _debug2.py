import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("SECRET_KEY", "debug-secret")

from dotenv import load_dotenv

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

import logging

logging.basicConfig(level=logging.DEBUG)

from Backend.app import create_app

app = create_app({"LOGIN_RATE_LIMIT": "1000 per minute"})
client = app.test_client()

client.post("/api/auth/login", json={
    "identifier": "QAADMIN01", "password": "QaVerify123", "role": "admin"})
csrf = client.get("/api/auth/me").get_json()["csrf_token"]

for course_id in (4,):
    response = client.post("/api/admin/attendance", json={
        "person_type": "student", "person_id": 13, "course_id": course_id,
        "date": "2026-10-01", "status": "present",
    }, headers={"X-CSRF-Token": csrf})
    print(f"course {course_id} ->", response.status_code, response.get_json())

report = client.get("/api/admin/attendance/report?person_type=student&person_id=13&course_id=4")
print("report ->", report.status_code, report.get_json())