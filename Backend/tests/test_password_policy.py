import unittest

from Backend.routes.admin import _password
from Backend.utils import generate_memorable_password, validate_password


class PasswordPolicyTests(unittest.TestCase):
    def test_rejects_password_without_a_letter_or_number(self):
        for password in ("12345678", "password"):
            with self.subTest(password=password), self.assertRaises(ValueError):
                validate_password(password)

    def test_accepts_password_with_letter_and_number(self):
        self.assertEqual(validate_password("DmSkill1"), "DmSkill1")

    def test_account_creation_requires_matching_password_and_confirmation(self):
        with self.assertRaisesRegex(ValueError, "Password is required"):
            _password({})
        with self.assertRaisesRegex(ValueError, "Passwords do not match"):
            _password({"password": "DmSkill1", "confirm_password": "DmSkill2"})
        self.assertEqual(
            _password({"password": "DmSkill1", "confirm_password": "DmSkill1"}),
            "DmSkill1",
        )

    def test_memorable_passwords_are_valid_and_use_fresh_random_values(self):
        passwords = {generate_memorable_password() for _ in range(20)}
        self.assertEqual(len(passwords), 20)
        for password in passwords:
            validate_password(password)


if __name__ == "__main__":
    unittest.main()
