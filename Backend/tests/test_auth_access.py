import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from werkzeug.security import generate_password_hash

os.environ.setdefault("SECRET_KEY", "test-only-secret-key")

from Backend.app import app


class FakeCursor:
    def __init__(self, user):
        self.user = user

    def execute(self, _query, _params=None):
        return None

    def fetchone(self):
        return self.user


class PasswordChangeCursor(FakeCursor):
    def __init__(self, user, password_hash):
        super().__init__(user)
        self.password_hash = password_hash
        self.query = ""
        self.connection = self
        self.statements = []

    def execute(self, query, _params=None):
        self.query = query
        self.statements.append(query)

    def fetchone(self):
        if "SELECT password_hash" in self.query:
            return {"password_hash": self.password_hash}
        if "SELECT auth_version" in self.query:
            return {"auth_version": 1}
        return self.user

    def commit(self):
        return None


class AuthenticationAccessTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_protected_admin_api_rejects_unauthenticated_request(self):
        response = self.client.get("/api/admin/dashboard")
        self.assertEqual(response.status_code, 401)

    def test_login_rejects_missing_credentials_without_database_access(self):
        response = self.client.post("/api/auth/login", json={})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Invalid ID or password.")

    def test_admin_api_checks_database_role_not_client_session_role(self):
        student = {
            "id": 7,
            "login_id": "DM20260007",
            "role": "student",
            "status": "active",
            "auth_version": 0,
            "must_change_password": False,
        }

        @contextmanager
        def fake_cursor(**_kwargs):
            yield FakeCursor(student)

        with self.client.session_transaction() as session:
            session["user_id"] = 7
            session["role"] = "admin"
            session["auth_version"] = 0

        with patch("Backend.utils.cursor", fake_cursor):
            response = self.client.get("/api/admin/dashboard")
        self.assertEqual(response.status_code, 403)

    def test_stale_auth_version_expires_session(self):
        student = {
            "id": 7,
            "login_id": "DM20260007",
            "role": "student",
            "status": "active",
            "auth_version": 1,
            "must_change_password": False,
        }

        @contextmanager
        def fake_cursor(**_kwargs):
            yield FakeCursor(student)

        with self.client.session_transaction() as session:
            session["user_id"] = 7
            session["auth_version"] = 0

        with patch("Backend.utils.cursor", fake_cursor):
            response = self.client.get("/api/admin/dashboard")
        self.assertEqual(response.status_code, 401)

    def test_temporary_password_blocks_portal_apis(self):
        student = {
            "id": 7,
            "login_id": "DM20260007",
            "role": "student",
            "status": "active",
            "auth_version": 0,
            "must_change_password": True,
        }

        @contextmanager
        def fake_cursor(**_kwargs):
            yield FakeCursor(student)

        with self.client.session_transaction() as session:
            session["user_id"] = 7
            session["auth_version"] = 0

        with patch("Backend.utils.cursor", fake_cursor):
            response = self.client.get("/api/portal/overview")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.get_json()["error"],
            "You must change your password before continuing.",
        )

    def test_temporary_password_user_can_change_password_and_clear_gate(self):
        student = {
            "id": 7,
            "login_id": "DM20260007",
            "role": "student",
            "status": "active",
            "auth_version": 0,
            "must_change_password": True,
        }
        old_hash = generate_password_hash("OldPass1", method="scrypt")
        auth_cursor = PasswordChangeCursor(student, old_hash)
        route_cursor = PasswordChangeCursor(student, old_hash)

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
            "Backend.routes.auth.cursor", fake_route_cursor
        ):
            response = self.client.post(
                "/api/auth/change-password",
                json={
                    "current_password": "OldPass1",
                    "new_password": "DmSkill1",
                    "confirm_password": "DmSkill1",
                },
                headers={"X-CSRF-Token": "test-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any("must_change_password = FALSE" in query for query in route_cursor.statements)
        )
        with self.client.session_transaction() as session:
            self.assertEqual(session["auth_version"], 1)

    def test_logout_requires_csrf_token(self):
        admin = {
            "id": 2,
            "login_id": "admin",
            "role": "admin",
            "status": "active",
            "auth_version": 0,
            "must_change_password": False,
        }

        @contextmanager
        def fake_cursor(**_kwargs):
            yield FakeCursor(admin)

        with self.client.session_transaction() as session:
            session["user_id"] = 2
            session["auth_version"] = 0
            session["csrf_token"] = "session-token"

        with patch("Backend.utils.cursor", fake_cursor):
            rejected = self.client.post("/api/auth/logout")
            accepted = self.client.post(
                "/api/auth/logout",
                headers={"X-CSRF-Token": "session-token"},
            )
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(accepted.status_code, 200)


if __name__ == "__main__":
    unittest.main()
