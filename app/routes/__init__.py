"""
Routes package initialization.
Registers all API blueprints with the Flask application.
"""
from flask import Flask

from app.routes.attendance import attendance_bp
from app.routes.auth import auth_bp
from app.routes.dashboard import dashboard_bp
from app.routes.exams import exams_bp
from app.routes.questions import questions_bp
from app.routes.results import results_bp
from app.routes.students import students_bp
from app.routes.submissions import submissions_bp
from app.routes.users import users_bp


def register_blueprints(app: Flask) -> None:
    """Register all modular route blueprints."""
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(exams_bp)
    app.register_blueprint(questions_bp)
    app.register_blueprint(submissions_bp)
    app.register_blueprint(dashboard_bp)
