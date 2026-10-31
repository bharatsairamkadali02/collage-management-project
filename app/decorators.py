"""
Role-Based Access Control (RBAC) decorators and security guards.
"""
from functools import wraps
from typing import Callable, Sequence
from flask import jsonify, request
from flask_login import current_user


def roles_required(*allowed_roles: str) -> Callable:
    """
    Decorator to restrict route access to users with specified roles.
    Returns 401 if unauthenticated, 403 if unauthorized.
    """
    roles_set = {r.lower().strip() for r in allowed_roles}

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({
                    "error": "Unauthorized",
                    "message": "Authentication required to access this resource.",
                }), 401

            if not current_user.is_active:
                return jsonify({
                    "error": "AccountDisabled",
                    "message": "Your account has been disabled. Contact an administrator.",
                }), 403

            user_role = (current_user.role or "").lower().strip()
            if user_role not in roles_set:
                return jsonify({
                    "error": "Forbidden",
                    "message": f"Access denied. Requires one of the following roles: {', '.join(sorted(roles_set))}.",
                }), 403

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def admin_required(fn: Callable) -> Callable:
    """Decorator requiring admin role."""
    return roles_required("admin")(fn)


def faculty_required(fn: Callable) -> Callable:
    """
    Decorator requiring faculty role.
    Admins are also granted access by virtue of administrative privileges.
    """
    return roles_required("admin", "faculty")(fn)


def student_required(fn: Callable) -> Callable:
    """
    Decorator requiring student role.
    """
    return roles_required("student")(fn)
