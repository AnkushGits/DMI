import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from mysql.connector import Error as MySQLError
from werkzeug.exceptions import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_ROOT = PROJECT_ROOT / "Frontend"
load_dotenv(PROJECT_ROOT / ".env")

from Backend.config import Config
from Backend.db import close_db
from Backend.extensions import limiter
from Backend.routes import admin, auth, chatbot, portal, public

def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY must be configured in the environment.")

    app.config["RATELIMIT_STORAGE_URI"] = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    limiter.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(portal.bp)
    app.register_blueprint(public.bp)
    app.register_blueprint(chatbot.bp)
    app.teardown_appcontext(close_db)

    @app.errorhandler(MySQLError)
    def handle_database_error(error):
        app.logger.exception("Database request failed", exc_info=error)
        return jsonify(error="The service is temporarily unavailable."), 503

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        app.logger.exception("Unhandled request error", exc_info=error)
        return jsonify(error="The request could not be completed."), 500

    @app.get("/")
    def homepage():
        return send_from_directory(FRONTEND_ROOT, "index.html")

    @app.get("/admin/login")
    @app.get("/student/login")
    @app.get("/employee/login")
    def login_alias():
        role = request.path.split("/")[1]
        return send_from_directory(FRONTEND_ROOT / role, "login.html")

    @app.get("/admin/dashboard")
    @app.get("/student/dashboard")
    @app.get("/employee/dashboard")
    def dashboard_alias():
        role = request.path.split("/")[1]
        return send_from_directory(FRONTEND_ROOT / role, "dashboard.html")

    @app.get("/<path:page>")
    def public_page(page):
        public_pages = {
            "index.html", "courses.html", "why-us.html", "about.html", "contact.html",
            "faqs.html", "faculty.html", "reviews.html",
        }
        role_pages = {
            "admin-login.html": ("admin", "login.html"),
            "admin-dashboard.html": ("admin", "dashboard.html"),
            "student-login.html": ("student", "login.html"),
            "student-dashboard.html": ("student", "dashboard.html"),
            "employee-login.html": ("employee", "login.html"),
            "employee-dashboard.html": ("employee", "dashboard.html"),
        }
        if page in public_pages:
            return send_from_directory(FRONTEND_ROOT, page)
        if page in role_pages:
            role, filename = role_pages[page]
            return send_from_directory(FRONTEND_ROOT / role, filename)
        if page.startswith(("assets/", "css/", "js/")):
            return send_from_directory(FRONTEND_ROOT, page)
        return jsonify(error="Not found."), 404

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    return app





# if __name__ == "__main__":
#     app.run(
#         host=os.environ.get("HOST", "127.0.0.1"),
#         port=int(os.environ.get("PORT", "5000")),
#         debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true",
#     )
