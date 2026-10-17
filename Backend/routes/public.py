from flask import Blueprint, jsonify
from Backend.db import cursor

bp = Blueprint("public", __name__, url_prefix="/api")


@bp.get("/courses")
def public_courses():
    with cursor() as db:
        db.execute(
            """SELECT id, course_code, name, description, duration_months, fee
               FROM courses WHERE status = 'active' ORDER BY name"""
        )
        return jsonify(courses=db.fetchall())
