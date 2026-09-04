from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import User, ROLES, default_permissions_for_role, normalize_role
from app.decorators import require_permission, current_user

users_bp = Blueprint("users", __name__)


def _scope_query(q, user):
    if normalize_role(user.role) == "manufacturer":
        return q.filter_by(manufacturer_id=user.manufacturer_id)
    return q


def _canonical_role(role_text):
    """Matches a role string against ROLES case-insensitively, returning
    the canonical spelling ('Admin' / 'Manufacturer' / 'Employee') or
    None if it isn't one of the allowed roles."""
    t = (role_text or "").strip().lower()
    return next((r for r in ROLES if r.lower() == t), None)


@users_bp.get("")
@require_permission("users")
def list_users():
    user = current_user()
    rows = _scope_query(User.query, user).all()
    return jsonify([u.to_dict() for u in rows])


@users_bp.post("")
@require_permission("users")
def create_user():
    acting = current_user()
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    role_input = (data.get("role") or "").strip()
    password = data.get("password") or ""

    if not name or not email or not role_input:
        return jsonify({"error": "Name, email, and role are required."}), 400
    if not password:
        return jsonify({"error": "Set a password for this account."}), 400

    role = _canonical_role(role_input)
    if not role:
        return jsonify({"error": f"Role must be one of: {', '.join(ROLES)}."}), 400
    if normalize_role(acting.role) == "manufacturer" and role in ("Admin", "Manufacturer"):
        return jsonify({"error": "Admin and Manufacturer roles must be created by an Admin."}), 403
    if User.query.filter(User.email.ilike(email)).first():
        return jsonify({"error": "A user with that email already exists."}), 409

    manufacturer_id = acting.manufacturer_id if normalize_role(acting.role) == "manufacturer" else data.get("manufacturerId")

    permissions = data.get("permissions")
    if permissions is None:
        permissions = default_permissions_for_role(role)

    new_user = User(
        name=name, email=email, role=role,
        manufacturer_id=manufacturer_id, status="Active",
    )
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.flush()
    new_user.set_permissions(permissions)
    db.session.commit()
    return jsonify(new_user.to_dict()), 201


@users_bp.put("/<user_id>")
@require_permission("users")
def update_user(user_id):
    acting = current_user()
    target = _scope_query(User.query, acting).filter_by(id=user_id).first()
    if not target:
        return jsonify({"error": "User not found."}), 404

    data = request.get_json(silent=True) or {}
    if "name" in data:
        target.name = data["name"]
    if "email" in data:
        target.email = data["email"].strip().lower()
    if "role" in data:
        role = _canonical_role(data["role"])
        if not role:
            return jsonify({"error": f"Role must be one of: {', '.join(ROLES)}."}), 400
        if normalize_role(acting.role) == "manufacturer" and role in ("Admin", "Manufacturer"):
            return jsonify({"error": "Admin and Manufacturer roles must be created by an Admin."}), 403
        target.role = role
    if "permissions" in data:
        target.set_permissions(data["permissions"])
    if data.get("password"):
        target.set_password(data["password"])

    db.session.commit()
    return jsonify(target.to_dict())


@users_bp.post("/<user_id>/toggle-status")
@require_permission("users")
def toggle_status(user_id):
    acting = current_user()
    target = _scope_query(User.query, acting).filter_by(id=user_id).first()
    if not target:
        return jsonify({"error": "User not found."}), 404
    target.status = "Inactive" if target.status == "Active" else "Active"
    db.session.commit()
    return jsonify(target.to_dict())


@users_bp.put("/<user_id>/permissions/<permission_key>")
@require_permission("users")
def set_single_permission(user_id, permission_key):
    """Flips one permission's granted flag (true/false) without
    touching the rest of the user's grants — e.g. {"granted": false}
    to revoke just that page while keeping the row/history."""
    acting = current_user()
    target = _scope_query(User.query, acting).filter_by(id=user_id).first()
    if not target:
        return jsonify({"error": "User not found."}), 404

    data = request.get_json(silent=True) or {}
    granted = bool(data.get("granted", True))
    target.set_permission(permission_key, granted)
    db.session.commit()
    return jsonify(target.to_dict())
