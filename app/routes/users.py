"""
User management API endpoints.
Accessible exclusively to Administrators for user lifecycle and credential administration.
"""
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user

from app.decorators import admin_required
from app.models.user import User
from app.services.audit import log_action
from app.services.dynamo import get_dynamo_service
from app.utils.helpers import paginate
from app.utils.validators import validate_password, validate_user_payload

users_bp = Blueprint("users", __name__, url_prefix="/api/users")


@users_bp.route("", methods=["GET"])
@admin_required
def list_users():
    """
    List all users with optional filtering by role or status.
    Supports pagination.
    """
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_USERS", "cms_users")

    role_filter = request.args.get("role")
    status_filter = request.args.get("status")
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))

    try:
        items = dynamo.scan(table_name=table_name)
        # Apply in-memory filtering for flexible admin search
        if role_filter:
            items = [u for u in items if u.get("role") == role_filter.lower()]
        if status_filter:
            items = [u for u in items if u.get("status") == status_filter.lower()]

        # Strip password_hash from response
        for item in items:
            item.pop("password_hash", None)

        # Sort by username
        items.sort(key=lambda x: x.get("username", ""))

        result = paginate(items, page=page, page_size=page_size)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@users_bp.route("/<string:username>", methods=["GET"])
@admin_required
def get_user(username: str):
    """Retrieve full profile details for a specific user."""
    user = User.get_by_username(username)
    if not user:
        return jsonify({"error": "NotFound", "message": f"User '{username}' not found."}), 404

    return jsonify({"user": user.to_dict()}), 200


@users_bp.route("", methods=["POST"])
@admin_required
def create_user():
    """Create a new user account."""
    data = request.get_json(silent=True) or {}
    is_valid, err_msg = validate_user_payload(data, is_update=False)
    if not is_valid:
        return jsonify({"error": "ValidationError", "message": err_msg}), 400

    username = data["username"].strip()
    email = data["email"].strip().lower()

    if User.get_by_username(username):
        return jsonify({"error": "Conflict", "message": f"Username '{username}' already exists."}), 409
    if User.get_by_email(email):
        return jsonify({"error": "Conflict", "message": f"Email '{email}' already registered."}), 409

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
        log_action(current_user.username, "USER_CREATED", f"user:{username}", f"Role: {new_user.role}")
        return jsonify({"message": "User created successfully.", "user": new_user.to_dict()}), 201
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@users_bp.route("/<string:username>", methods=["PUT"])
@admin_required
def update_user(username: str):
    """Update profile attributes for a user (email, full_name, role, linked_id)."""
    user = User.get_by_username(username)
    if not user:
        return jsonify({"error": "NotFound", "message": f"User '{username}' not found."}), 404

    data = request.get_json(silent=True) or {}
    is_valid, err_msg = validate_user_payload(data, is_update=True)
    if not is_valid:
        return jsonify({"error": "ValidationError", "message": err_msg}), 400

    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_USERS", "cms_users")

    update_expr = []
    expr_names = {}
    expr_values = {}

    if "email" in data:
        update_expr.append("#em = :em")
        expr_names["#em"] = "email"
        expr_values[":em"] = data["email"].strip().lower()

    if "full_name" in data:
        update_expr.append("#fn = :fn")
        expr_names["#fn"] = "full_name"
        expr_values[":fn"] = data["full_name"].strip()

    if "role" in data:
        update_expr.append("#ro = :ro")
        expr_names["#ro"] = "role"
        expr_values[":ro"] = data["role"].strip().lower()

    if "linked_id" in data:
        update_expr.append("#li = :li")
        expr_names["#li"] = "linked_id"
        expr_values[":li"] = data["linked_id"]

    if not update_expr:
        return jsonify({"message": "No fields to update.", "user": user.to_dict()}), 200

    try:
        updated = dynamo.update_item(
            table_name=table_name,
            key={"username": username},
            update_expression="SET " + ", ".join(update_expr),
            expression_attribute_names=expr_names,
            expression_attribute_values=expr_values,
        )
        updated.pop("password_hash", None)
        log_action(current_user.username, "USER_UPDATED", f"user:{username}", "Admin updated attributes")
        return jsonify({"message": "User updated successfully.", "user": updated}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@users_bp.route("/<string:username>/status", methods=["PATCH"])
@admin_required
def update_user_status(username: str):
    """Enable or disable a user account."""
    if username == current_user.username:
        return jsonify({"error": "BadRequest", "message": "You cannot disable your own administrator account."}), 400

    data = request.get_json(silent=True) or {}
    new_status = data.get("status", "").lower().strip()
    if new_status not in ("active", "disabled"):
        return jsonify({"error": "ValidationError", "message": "Status must be 'active' or 'disabled'."}), 400

    user = User.get_by_username(username)
    if not user:
        return jsonify({"error": "NotFound", "message": f"User '{username}' not found."}), 404

    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_USERS", "cms_users")

    try:
        updated = dynamo.update_item(
            table_name=table_name,
            key={"username": username},
            update_expression="SET #st = :st",
            expression_attribute_names={"#st": "status"},
            expression_attribute_values={":st": new_status},
        )
        updated.pop("password_hash", None)
        log_action(current_user.username, "USER_STATUS_CHANGED", f"user:{username}", f"Status set to {new_status}")
        return jsonify({"message": f"User status updated to {new_status}.", "user": updated}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@users_bp.route("/<string:username>/reset-password", methods=["POST"])
@admin_required
def reset_user_password(username: str):
    """Admin resets a user's password."""
    user = User.get_by_username(username)
    if not user:
        return jsonify({"error": "NotFound", "message": f"User '{username}' not found."}), 404

    data = request.get_json(silent=True) or {}
    new_password = data.get("new_password")
    is_valid, err_msg = validate_password(new_password)
    if not is_valid:
        return jsonify({"error": "ValidationError", "message": err_msg}), 400

    try:
        user.update_password(new_password)
        log_action(current_user.username, "USER_PASSWORD_RESET", f"user:{username}", "Admin reset password")
        return jsonify({"message": f"Password reset successfully for user '{username}'."}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@users_bp.route("/<string:username>", methods=["DELETE"])
@admin_required
def delete_user(username: str):
    """Delete a user account."""
    if username == current_user.username:
        return jsonify({"error": "BadRequest", "message": "You cannot delete your own administrator account."}), 400

    user = User.get_by_username(username)
    if not user:
        return jsonify({"error": "NotFound", "message": f"User '{username}' not found."}), 404

    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_USERS", "cms_users")

    try:
        dynamo.delete_item(table_name=table_name, key={"username": username})
        log_action(current_user.username, "USER_DELETED", f"user:{username}", "User permanently deleted")
        return jsonify({"message": f"User '{username}' deleted successfully."}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500
