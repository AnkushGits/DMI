import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-only-secret-key")

from Backend.app import app


class FakeConnection:
    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True


class FakeCursor:
    def __init__(self, fetch_result=None):
        self.fetch_result = fetch_result
        self.query = ""
        self.params = None
        self.connection = FakeConnection()

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchone(self):
        if "FROM users WHERE id" in self.query:
            return {
                "id": 7,
                "login_id": "DM20260007",
                "role": "student",
                "status": "active",
                "auth_version": 0,
                "must_change_password": False,
            }
        return self.fetch_result


class PortalProfileTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_student_can_update_contact_fields_but_not_protected_fields(self):
        auth_cursor = FakeCursor()
        route_cursor = FakeCursor(fetch_result={"id": 12})

        @contextmanager
        def fake_auth_cursor(**_kwargs):
            yield auth_cursor

        @contextmanager
        def fake_route_cursor(**_kwargs):
            yield route_cursor

        with self.client.session_transaction() as session:
            session["user_id"] = 7
            session["auth_version"] = 0
            session["csrf_token"] = "test-token"

        with patch("Backend.utils.cursor", fake_auth_cursor), patch(
            "Backend.routes.portal.cursor", fake_route_cursor
        ):
            response = self.client.put(
                "/api/portal/profile",
                json={
                    "phone": "9876543210",
                    "student_id": "DM99999999",
                    "status": "inactive",
                    "role": "admin",
                },
                headers={"X-CSRF-Token": "test-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("UPDATE students SET phone = %s", route_cursor.query)
        self.assertNotIn("status", route_cursor.query)
        self.assertNotIn("student_id", route_cursor.query)
        self.assertTrue(route_cursor.connection.committed)


if __name__ == "__main__":
    unittest.main()
