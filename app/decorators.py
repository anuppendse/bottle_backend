from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity

from app.models import User, normalize_role, get_user_permissions, RecordStatus

# Mirrors ROLE_ALLOWED in the frontend mock — which system roles may hit
# a given resource at all, independent of the per-user permissions list.
ROLE_ALLOWED = {
    "dashboard": ["admin", "manufacturer"],
    "users": ["admin", "manufacturer"],
    "products": ["admin", "manufacturer", "employee"],
    "labelGeneration": ["admin", "manufacturer"],
    "dispatchConsole": ["admin", "manufacturer"],
    "batches": ["admin", "manufacturer"],
    "recalls": ["admin", "manufacturer"],
    "csvDownloads": ["admin", "manufacturer", "employee"],
    "csvRequests": ["admin"],
    "setup": ["admin"],
}


def current_user():
    uid = get_jwt_identity()
    return User.query.get(uid)


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user = current_user()
        
        if not user or user.status != RecordStatus.ACTIVE:
            return jsonify({"error": "Account is inactive or not found."}), 401
        return fn(*args, **kwargs)
    return wrapper


def require_permission(resource_key):
    """Checks both the system-role allowlist AND the user's own granted
    permissions (except 'setup', which is Admin-only and never assignable),
    matching the frontend's goTo()/ROLE_ALLOWED + sidebar permission logic.
    Uses normalize_role()/get_user_permissions() directly instead of the
    old User.system_role / User.permissions properties."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = current_user()
            if not user or user.status != RecordStatus.ACTIVE:
                return jsonify({"error": "Account is inactive or not found."}), 401
            role = normalize_role(user.role)
            allowed_roles = ROLE_ALLOWED.get(resource_key, [])
            
            if allowed_roles and role not in allowed_roles:
                return jsonify({"error": "403 — access denied for your role."}), 403
            if resource_key == "setup":
                if role != "admin":
                    return jsonify({"error": "403 — Setup is Admin only."}), 403
            """
            elif role != "admin" and resource_key not in get_user_permissions(user.id):
                return jsonify({"error": "403 — this page isn't in your granted permissions."}), 403
            """
            return fn(*args, **kwargs)
          
        return wrapper
    return decorator


def require_role(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = current_user()
            if not user or user.status != RecordStatus.ACTIVE:
                return jsonify({"error": "Account is inactive or not found."}), 401
            if normalize_role(user.role) not in roles:
                return jsonify({"error": "403 — access denied for your role."}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator
