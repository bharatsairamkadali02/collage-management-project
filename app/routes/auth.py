"""
Authentication API endpoints: login, logout, registration, and password management.
"""
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required, login_user, logout_user

from app.decorators import admin_required
from app.models.user import User
from app.services.audit import log_action
from app.utils.helpers import RateLimiter
from app.utils.validators import validate_password, validate_user_payload

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Per-IP rate limiter instance for login endpoint (5 attempts / minute)
login_limiter = RateLimiter(max_requests=5, window_seconds=60)


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Authenticate user with username and password.
    Rate limited to max 5 attempts per minute per IP.
    """
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")
    allowed, remaining = login_limiter.is_allowed(client_ip)
    if not allowed:
        log_action("anonymous", "LOGIN_BLOCKED", "auth", f"Rate limit exceeded from {client_ip}", client_ip)
        return jsonify({
            "error": "TooManyRequests",
            "message": "Too many failed login attempts. Please wait 1 minute before trying again.",
        }), 429

    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({
            "error": "BadRequest",
            "message": "Both username and password are required.",
        }), 400

    user = User.get_by_username(username)
    if not user or not user.check_password(password):
        log_action(username or "anonymous", "LOGIN_FAILED", "auth", f"Invalid credentials from {client_ip}", client_ip)
        return jsonify({
            "error": "Unauthorized",
            "message": "Invalid username or password.",
        }), 401

    if not user.is_active:
        log_action(username, "LOGIN_FAILED_DISABLED", "auth", "Account disabled", client_ip)
        return jsonify({
            "error": "AccountDisabled",
            "message": "Account has been deactivated. Please contact an administrator.",
        }), 403

    # Log in session
    login_user(user, remember=True)
    user.update_last_login()
    login_limiter.reset(client_ip)

    log_action(user.username, "LOGIN_SUCCESS", "auth", f"Successful login from {client_ip}", client_ip)

    return jsonify({
        "message": "Login successful.",
        "user": user.to_dict(),
    }), 200


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Log out current user and terminate session."""
    username = current_user.username
    logout_user()
    log_action(username, "LOGOUT", "auth", "User logged out")
    return jsonify({"message": "Successfully logged out."}), 200


@auth_bp.route("/me", methods=["GET"])
@login_required
def get_current_user_profile():
    """Return currently authenticated user's profile."""
    return jsonify({
        "user": current_user.to_dict(),
    }), 200


@auth_bp.route("/register", methods=["POST"])
@admin_required
def register_user():
    """
    Create a new user. Strictly restricted to Administrators.
    """
    data = request.get_json(silent=True) or {}
    is_valid, err_msg = validate_user_payload(data, is_update=False)
    if not is_valid:
        return jsonify({"error": "ValidationError", "message": err_msg}), 400

    username = data["username"].strip()
    email = data["email"].strip().lower()

    # Check if user already exists
    if User.get_by_username(username):
        return jsonify({"error": "Conflict", "message": f"Username '{username}' is already taken."}), 409

    if User.get_by_email(email):
        return jsonify({"error": "Conflict", "message": f"Email '{email}' is already registered."}), 409

    try:
        new_user = User.create(
            username=username,
            email=email,
            password=data["password"],
            role=data["role"],
            full_name=data["full_name"],
            linked_id=data.get("linked_id"),
            status=data.get("status", "active"),
        )
        log_action(
            current_user.username,
            "USER_CREATED",
            f"user:{username}",
            f"Created user with role {new_user.role}",
        )
        return jsonify({
            "message": "User registered successfully.",
            "user": new_user.to_dict(),
        }), 201
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    """Allow logged-in user to change their own password."""
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not current_password or not new_password:
        return jsonify({
            "error": "BadRequest",
            "message": "Both current_password and new_password are required.",
        }), 400

    if not current_user.check_password(current_password):
        return jsonify({
            "error": "Unauthorized",
            "message": "Current password is incorrect.",
        }), 401

    is_valid, err = validate_password(new_password)
    if not is_valid:
        return jsonify({"error": "ValidationError", "message": err}), 400

    try:
        current_user.update_password(new_password)
        log_action(current_user.username, "PASSWORD_CHANGED", "auth", "User changed own password")
        return jsonify({"message": "Password changed successfully."}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500
