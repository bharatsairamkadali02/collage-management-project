"""
Flask application factory with Socket.IO, CORS, Flask-Login, and secure headers.
"""
import logging
import os
from flask import Flask, jsonify, request
from flask_cors import CORS

from app.config import config_by_name
from app.extensions import bcrypt, login_manager, socketio
from app.models.user import User
from app.routes import register_blueprints
from app.sockets.events import register_socket_events


def create_app(config_name: str = "development") -> Flask:
    """
    Construct and configure the Flask application instance.
    """
    app = Flask(__name__)

    # Load configuration
    config_cls = config_by_name.get(config_name, config_by_name["default"])
    app.config.from_object(config_cls)

    # Set up application logging
    logging.basicConfig(
        level=logging.INFO if not app.config.get("DEBUG") else logging.DEBUG,
        format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    )

    # Initialize extensions
    bcrypt.init_app(app)
    login_manager.init_app(app)

    # Initialize CORS with configured allowed origins
    allowed_origins = app.config.get("CORS_ALLOWED_ORIGINS", "*")
    CORS(
        app,
        resources={r"/api/*": {"origins": allowed_origins}},
        supports_credentials=True,
    )

    # Initialize Socket.IO
    # Use eventlet worker when available
    async_mode = "eventlet" if not app.config.get("TESTING") else "threading"
    socketio.init_app(
        app,
        cors_allowed_origins=allowed_origins,
        async_mode=async_mode,
        manage_session=False,
    )

    # Register Socket.IO listeners
    register_socket_events(socketio)

    # Configure Flask-Login
    @login_manager.user_loader
    def load_user(username: str):
        return User.get_by_username(username)

    @login_manager.unauthorized_handler
    def unauthorized_callback():
        return jsonify({
            "error": "Unauthorized",
            "message": "Authentication required. Please log in.",
        }), 401

    # Security Headers Middleware
    @app.after_request
    def apply_security_headers(response):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        if not app.config.get("DEBUG") and not app.config.get("TESTING"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # Health check endpoint
    @app.route("/api/health", methods=["GET"])
    def health_check():
        return jsonify({
            "status": "healthy",
            "service": "college-management-system-backend",
            "version": "1.0.0",
        }), 200

    # Global Error Handlers (all returning clean JSON)
    @app.errorhandler(400)
    def handle_bad_request(err):
        return jsonify({
            "error": "BadRequest",
            "message": getattr(err, "description", "Malformed request syntax."),
        }), 400

    @app.errorhandler(401)
    def handle_unauthorized(err):
        return jsonify({
            "error": "Unauthorized",
            "message": getattr(err, "description", "Authentication required."),
        }), 401

    @app.errorhandler(403)
    def handle_forbidden(err):
        return jsonify({
            "error": "Forbidden",
            "message": getattr(err, "description", "Insufficient permissions for this resource."),
        }), 403

    @app.errorhandler(404)
    def handle_not_found(err):
        return jsonify({
            "error": "NotFound",
            "message": getattr(err, "description", "The requested resource does not exist."),
        }), 404

    @app.errorhandler(429)
    def handle_too_many_requests(err):
        return jsonify({
            "error": "TooManyRequests",
            "message": getattr(err, "description", "Rate limit exceeded. Please wait before retrying."),
        }), 429

    @app.errorhandler(500)
    def handle_internal_server_error(err):
        app.logger.error("Unhandled internal server error: %s", err)
        return jsonify({
            "error": "InternalServerError",
            "message": "An unexpected error occurred on the server.",
        }), 500

    # Register blueprints
    register_blueprints(app)

    return app
