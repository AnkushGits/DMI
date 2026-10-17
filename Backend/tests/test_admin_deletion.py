import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-only-secret-key")

from Backend.app import app


class FakeConnection:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    def start_transaction(self):
        return None

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakeCursor:
    def __init__(self, user=None, profile=None):
        self.user = user
        self.profile = profile
        self.connection = FakeConnection()
        self.queries = []
        self.query = ""

    def execute(self, query, params=None):
        self.query = query
        self.queries.append((query, params))

    def fetchone(self):
        if "FROM users WHERE id" in self.query:
            return self.user
        if "FROM students WHERE id" in self.query or "FROM employees WHERE id" in self.query:
            return self.profile
        return None


class AdminDeletionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_permanent_delete_requires_confirmation_and_removes_target_rows(self):
        admin_user = {
            "id": 2,
            "login_id": "admin",
            "role": "admin",
            "status": "active",
            "auth_version": 0,
            "must_change_password": False,
        }

        for kind, row_id, profile in (
            ("students", 17, {"user_id": 117}),
            ("employees", 23, {"user_id": 123}),
        ):
            route_cursor = FakeCursor(profile=profile)

            @contextmanager
            def fake_auth_cursor(**_kwargs):
                yield FakeCursor(user=admin_user)

            @contextmanager
            def fake_route_cursor(**_kwargs):
                yield route_cursor

            with self.client.session_transaction() as session:
                session["user_id"] = admin_user["id"]
                session["auth_version"] = admin_user["auth_version"]
                session["csrf_token"] = "test-token"

            with patch("Backend.utils.cursor", fake_auth_cursor), patch(
                "Backend.routes.admin.cursor", fake_route_cursor
            ):
                response = self.client.delete(
                    f"/api/admin/{kind}/{row_id}",
                    json={"confirmation": "DELETE"},
                    headers={"X-CSRF-Token": "test-token"},
                )

            self.assertEqual(response.status_code, 200)
            self.assertTrue(route_cursor.connection.committed)
            statements = [query.lower() for query, _params in route_cursor.queries]
            self.assertTrue(any(f"delete from {kind}" in query for query in statements))
            self.assertTrue(any("delete from users" in query for query in statements))
            self.assertFalse(any(f"update {kind} set status = 'inactive'" in query for query in statements))

    def test_permanent_delete_requires_exact_confirmation(self):
        admin_user = {
            "id": 2,
            "login_id": "admin",
            "role": "admin",
            "status": "active",
            "auth_version": 0,
            "must_change_password": False,
        }

        @contextmanager
        def fake_auth_cursor(**_kwargs):
            yield FakeCursor(user=admin_user)

        route_cursor = FakeCursor(profile={"user_id": 117})

        @contextmanager
        def fake_route_cursor(**_kwargs):
            yield route_cursor

        with self.client.session_transaction() as session:
            session["user_id"] = admin_user["id"]
            session["auth_version"] = admin_user["auth_version"]
            session["csrf_token"] = "test-token"

        with patch("Backend.utils.cursor", fake_auth_cursor), patch(
            "Backend.routes.admin.cursor", fake_route_cursor
        ):
            response = self.client.delete(
                "/api/admin/students/17",
                json={"confirmation": "DELETE "},
                headers={"X-CSRF-Token": "test-token"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(route_cursor.queries)


if __name__ == "__main__":
    unittest.main()
