import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-only-secret-key")

from Backend.app import app


class FakeConnection:
    def __init__(self):
        self.committed = False
        self.in_transaction = False

    def commit(self):
        self.committed = True

    def start_transaction(self, *args, **kwargs):
        self.in_transaction = True

    def rollback(self):
        self.committed = False


class FakeCursor:
    """Answers only the queries the attendance routes actually issue."""

    def __init__(self, *, user=None, enrollment=None, employee=True, existing=None, rows=None):
        self.user = user
        self.enrollment = enrollment
        self.employee = employee
        self.existing = existing
        self.rows = rows or []
        self.queries = []
        self.lastrowid = 42
        self.rowcount = 1
        self.connection = FakeConnection()

    def execute(self, query, params=None):
        self.queries.append((query, params))
        if "INSERT INTO attendance" in query or "INSERT INTO employee_attendance" in query:
            self.lastrowid = 42

    def fetchone(self):
        joined = self.queries[-1][0] if self.queries else ""
        if "FROM users WHERE id" in joined:
            return self.user
        if "FROM student_courses sc" in joined:
            return self.enrollment
        if "FROM employees WHERE id" in joined:
            return {"id": 1} if self.employee else None
        if "SELECT a.id, a.status" in joined or "SELECT ea.id, ea.status" in joined:
            return self.existing
        return None

    def fetchall(self):
        return self.rows

    def last_query(self):
        return self.queries[-1][0] if self.queries else ""


class AdminAttendanceTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.admin = {
            "id": 2,
            "login_id": "admin",
            "role": "admin",
            "status": "active",
            "auth_version": 0,
            "must_change_password": False,
        }
        with self.client.session_transaction() as session:
            session["user_id"] = self.admin["id"]
            session["auth_version"] = self.admin["auth_version"]
            session["csrf_token"] = "test-token"

    def _patch_cursors(self, route_cursor):
        @contextmanager
        def fake_auth_cursor(**_kwargs):
            yield FakeCursor(user=self.admin)

        @contextmanager
        def fake_route_cursor(**_kwargs):
            yield route_cursor

        return (
            patch("Backend.utils.cursor", fake_auth_cursor),
            patch("Backend.routes.admin.cursor", fake_route_cursor),
        )

    def _post(self, payload):
        return self.client.post(
            "/api/admin/attendance",
            json=payload,
            headers={"X-CSRF-Token": "test-token"},
        )

    def test_admin_can_create_attendance_for_an_enrolled_student(self):
        route_cursor = FakeCursor(enrollment={"employee_id": 9})
        auth_patch, route_patch = self._patch_cursors(route_cursor)
        with auth_patch, route_patch:
            response = self._post({
                "person_type": "student",
                "person_id": 17,
                "course_id": 3,
                "date": "2026-10-03",
                "status": "present",
                "remarks": "On time",
            })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["attendance_id"], 42)
        self.assertTrue(route_cursor.connection.committed)
        self.assertIn("INSERT INTO attendance", route_cursor.last_query())

    def test_saving_over_an_existing_record_updates_instead_of_failing(self):
        """Replaces the old behaviour where a duplicate returned a dead-end 409."""
        route_cursor = FakeCursor(enrollment={"employee_id": 9})
        auth_patch, route_patch = self._patch_cursors(route_cursor)
        with auth_patch, route_patch:
            response = self._post({
                "person_type": "student",
                "person_id": 17,
                "course_id": 3,
                "date": "2026-10-03",
                "status": "absent",
            })

        self.assertEqual(response.status_code, 201)
        query = route_cursor.last_query()
        self.assertIn("ON DUPLICATE KEY UPDATE", query)
        self.assertIn("status = VALUES(status)", query)
        self.assertTrue(route_cursor.connection.committed)

    def test_employee_attendance_is_recorded_without_a_course(self):
        route_cursor = FakeCursor(enrollment={"employee_id": 9}, employee=True)
        auth_patch, route_patch = self._patch_cursors(route_cursor)
        with auth_patch, route_patch:
            response = self._post({
                "person_type": "employee",
                "person_id": 4,
                "date": "2026-10-03",
                "status": "half_day",
            })

        self.assertEqual(response.status_code, 201)
        self.assertIn("INSERT INTO employee_attendance", route_cursor.last_query())
        self.assertIn("ON DUPLICATE KEY UPDATE", route_cursor.last_query())

    def test_half_day_is_rejected_for_students(self):
        route_cursor = FakeCursor(enrollment={"employee_id": 9})
        auth_patch, route_patch = self._patch_cursors(route_cursor)
        with auth_patch, route_patch:
            response = self._post({
                "person_type": "student",
                "person_id": 17,
                "course_id": 3,
                "date": "2026-10-03",
                "status": "half_day",
            })

        self.assertEqual(response.status_code, 400)
        self.assertFalse(route_cursor.connection.committed)

    def test_unenrolled_student_cannot_receive_course_attendance(self):
        route_cursor = FakeCursor(enrollment=None)
        auth_patch, route_patch = self._patch_cursors(route_cursor)
        with auth_patch, route_patch:
            response = self._post({
                "person_type": "student",
                "person_id": 17,
                "course_id": 3,
                "date": "2026-10-03",
                "status": "present",
            })

        self.assertEqual(response.status_code, 400)
        self.assertFalse(route_cursor.connection.committed)

    def test_lookup_reports_create_mode_when_no_record_exists(self):
        route_cursor = FakeCursor(existing=None)
        auth_patch, route_patch = self._patch_cursors(route_cursor)
        with auth_patch, route_patch:
            response = self.client.get(
                "/api/admin/attendance/lookup?person_type=student&person_id=17&course_id=3&date=2026-10-03"
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["found"])
        self.assertEqual(response.get_json()["mode"], "create")

    def test_lookup_reports_update_mode_and_returns_existing_record(self):
        existing = {
            "id": 7, "status": "present", "remarks": "On time",
            "attendance_date": "2026-10-03", "course_id": 3,
            "person_id": 17, "person_type": "student",
        }
        route_cursor = FakeCursor(existing=existing)
        auth_patch, route_patch = self._patch_cursors(route_cursor)
        with auth_patch, route_patch:
            response = self.client.get(
                "/api/admin/attendance/lookup?person_type=student&person_id=17&course_id=3&date=2026-10-03"
            )

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["found"])
        self.assertEqual(body["mode"], "update")
        self.assertEqual(body["record"]["status"], "present")

    def test_delete_targets_the_employee_table_for_employee_records(self):
        route_cursor = FakeCursor()
        auth_patch, route_patch = self._patch_cursors(route_cursor)
        with auth_patch, route_patch:
            response = self.client.delete(
                "/api/admin/attendance/7",
                json={"person_type": "employee"},
                headers={"X-CSRF-Token": "test-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("DELETE FROM employee_attendance", route_cursor.last_query())

    def test_portal_attendance_is_read_only(self):
        response = self.client.post(
            "/api/portal/attendance",
            json={"student_id": 17, "course_id": 3, "status": "present"},
        )
        self.assertEqual(response.status_code, 405)

    def test_unauthenticated_request_is_rejected(self):
        client = app.test_client()
        self.assertEqual(client.get("/api/admin/attendance").status_code, 401)


if __name__ == "__main__":
    unittest.main()