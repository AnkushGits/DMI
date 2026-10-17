import secrets
from functools import wraps
from hmac import compare_digest
import re

from flask import current_app, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from Backend.db import cursor


def json_error(message, status):
    return jsonify(error=message), status


def require_role(*roles):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user_id = session.get("user_id")
            if not user_id:
                return json_error("Authentication required.", 401)

            try:
                with cursor() as db:
                    db.execute(
                        """SELECT id, login_id, role, status, auth_version, must_change_password
                           FROM users WHERE id = %s""",
                        (user_id,),
                    )
                    user = db.fetchone()
            except Exception:
                current_app.logger.exception("Could not validate authenticated user")
                return json_error("The service is temporarily unavailable.", 503)

            if (
                not user
                or user["status"] != "active"
                or user["auth_version"] != session.get("auth_version")
            ):
                session.clear()
                return json_error("Your session is no longer valid.", 401)
            if roles and user["role"] not in roles:
                return json_error("You are not authorized to access this resource.", 403)
            if user["must_change_password"] and request.endpoint not in (
                "auth.me",
                "auth.change_password",
                "auth.logout",
            ):
                return json_error("You must change your password before continuing.", 403)
            request.current_user = user
            return view(*args, **kwargs)

        return wrapped

    return decorate


def require_csrf(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        expected = session.get("csrf_token", "")
        supplied = request.headers.get("X-CSRF-Token", "")
        if not expected or not compare_digest(expected, supplied):
            return json_error("Invalid or expired request token.", 403)
        return view(*args, **kwargs)

    return wrapped


def new_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def hash_password(password):
    return generate_password_hash(password, method="scrypt")


def verify_password(password_hash, password):
    return check_password_hash(password_hash, password)


def validate_password(password):
    if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
        raise ValueError("Password must be between 8 and 128 characters.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValueError("Password must contain at least one letter and one number.")
    return password


_PASSWORD_WORDS = (
    "Amber", "Anchor", "Apple", "Apricot", "Archer", "Aspen", "Atlas", "Autumn",
    "Bamboo", "Beacon", "Berry", "Birch", "Blossom", "Breeze", "Cactus", "Canyon",
    "Cedar", "Charger", "Cherry", "Clover", "Cloud", "Comet", "Coral", "Cosmos",
    "Cricket", "Daisy", "Delta", "Dolphin", "Dragon", "Eagle", "Echo", "Ember",
    "Falcon", "Fern", "Flame", "Flute", "Forest", "Galaxy", "Garden", "Glacier",
    "Harbor", "Hazel", "Horizon", "Island", "Jasmine", "Jupiter", "Kestrel", "Lagoon",
    "Lantern", "Laurel", "Lemon", "Lotus", "Maple", "Marble", "Mango", "Meadow",
    "Meteor", "Midnight", "Mint", "Mountain", "Nectar", "Nova", "Ocean", "Olive",
    "Orchid", "Otter", "Pebble", "Pine", "Planet", "Prairie", "Quartz", "Quill",
    "Rain", "Raven", "Redwood", "River", "Robin", "Rocket", "Saffron", "Sailboat",
    "Sapphire", "Sequoia", "Silver", "Snow", "Solar", "Sparrow", "Spring", "Starling",
    "Summit", "Sunrise", "Thunder", "Tiger", "Topaz", "Tulip", "Velvet", "Violet",
    "Willow", "Winter", "Wren", "Zephyr",
)


def generate_memorable_password():
    first, second, third = secrets.SystemRandom().sample(_PASSWORD_WORDS, 3)
    symbol = secrets.choice("@#$%!")
    number = secrets.randbelow(9000) + 1000
    return f"{first}{symbol}{number}{second}{third}"


def validated_text(data, field, *, required=True, max_length=255):
    value = data.get(field)
    if value is None:
        if required:
            raise ValueError(f"{field.replace('_', ' ').capitalize()} is required.")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field.replace('_', ' ').capitalize()} must be text.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{field.replace('_', ' ').capitalize()} is required.")
    if len(value) > max_length:
        raise ValueError(f"{field.replace('_', ' ').capitalize()} is too long.")
    return value or None
