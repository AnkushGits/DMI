import os
import sys

from dotenv import load_dotenv
from mysql.connector import IntegrityError

from Backend.app import app
from Backend.db import cursor
from Backend.utils import hash_password


def main():
    load_dotenv()
    login_id = os.environ.get("ADMIN_LOGIN_ID", "").strip()
    password = os.environ.get("ADMIN_INITIAL_PASSWORD", "")
    full_name = os.environ.get("ADMIN_FULL_NAME", "").strip()
    if not login_id or len(password) < 12 or not full_name:
        raise SystemExit(
            "Set ADMIN_LOGIN_ID, ADMIN_INITIAL_PASSWORD (12+ characters), "
            "and ADMIN_FULL_NAME in .env before running this command."
        )
    with app.app_context():
        try:
            with cursor() as db:
                db.connection.start_transaction()
                db.execute(
                    "INSERT INTO users (login_id, password_hash, role) VALUES (%s, %s, 'admin')",
                    (login_id, hash_password(password)),
                )
                db.execute(
                    "INSERT INTO admins (user_id, full_name) VALUES (%s, %s)",
                    (db.lastrowid, full_name),
                )
                db.connection.commit()
        except IntegrityError:
            raise SystemExit("That admin login ID already exists.")
        except Exception:
            app.logger.exception("Admin account creation failed")
            raise SystemExit("Admin account could not be created. Check database configuration.")
    print(f"Admin account created for {login_id}.")


if __name__ == "__main__":
    main()
