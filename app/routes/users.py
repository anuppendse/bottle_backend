from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import (
    User,
    ROLES,
    default_permissions_for_role,
    normalize_role,
    Role,
    Manufacturer,
    RecordStatus,
)
from app.decorators import require_permission, current_user

users_bp = Blueprint("users", __name__)


def _scope_query(q, user):
    if normalize_role(user.role) == Role.MANUFACTURER.value:
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
    role = normalize_role(user.role)

    if role == Role.ADMIN.value.lower():
        rows = User.query.filter(
            User.role.in_([Role.MANUFACTURER.value, Role.EMPLOYEE.value])
        ).all()
    elif role == Role.MANUFACTURER.value.lower():
        rows = User.query.filter_by(
            manufacturer_id=user.manufacturer_id,
            role=Role.EMPLOYEE.value,
        ).all()
    else:
        rows = User.query.all()

    return jsonify([u.to_dict() for u in rows])

@users_bp.post("")
@require_permission("users")
def create_user():
    acting = current_user()

    data = request.get_json(silent=True) or {}

    name = data.get("name")
    email = data.get("email")
    username = data.get("username")
    role_input = data.get("role")
    password = data.get("password")
    manufacturer_id = data.get("manufacturer_id")

    if (
        not name
        or not email
        or not username
        or not role_input
        or not password
        or not manufacturer_id
    ):
        return (
            jsonify(
                {
                    "error": "Name, email, username, password , manufacturer_id and role,  are required."
                }
            ),
            400,
        )

    email = email.strip().lower()
    username = username.strip().lower()
    name = name.strip()

    if role_input:
        try:
            role = Role(role_input.strip().upper())
        except ValueError:
            return (jsonify({"error": f"Invalid role: {role_input}"}), 400)

    if acting.role == Role.MANUFACTURER.value and role != Role.EMPLOYEE.value:
        return (jsonify({"error": "Manufacturer can only create an employee"}), 403)

    manufacturer = Manufacturer.query.get(
        manufacturer_id=manufacturer_id, status=RecordStatus.ACTIVE
    )
    if not manufacturer:
        return (jsonify({"error": "Manufacturer not found"}), 404)

    user_with_email = User.query.filter(
        User.email.ilike(email), User.manufacturer_id == acting.manufacturer_id
    ).first()

    user_with_username = User.query.filter(
        User.username.ilike(username), User.manufacturer_id == acting.manufacturer_id
    ).first()

    if user_with_email or user_with_username:
        return (
            jsonify({"error": "A user with this username or  email already exists."}),
            409,
        )

    permissions = data.get("permissions")
    if permissions is None:
        permissions = default_permissions_for_role(role)

    new_user = User(
        name=name,
        email=email,
        username=username,
        role=role,
        manufacturer_id=manufacturer_id,
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
    if "username" in data:
        new_username = (data["username"] or "").strip().lower()
        if not new_username:
            return jsonify({"error": "Username cannot be empty."}), 400
        existing = User.query.filter(User.username.ilike(new_username)).first()
        if existing and existing.id != target.id:
            return jsonify({"error": "A user with that username already exists."}), 409
        target.username = new_username
    if "role" in data:
        role = _canonical_role(data["role"])
        if not role:
            return jsonify({"error": f"Role must be one of: {', '.join(ROLES)}."}), 400
        if normalize_role(acting.role) == "manufacturer" and role in (
            "Admin",
            "Manufacturer",
        ):
            return (
                jsonify(
                    {
                        "error": "Admin and Manufacturer roles must be created by an Admin."
                    }
                ),
                403,
            )
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


@users_bp.delete("/<user_id>")
@require_permission("users")
def delete_user(user_id):
    acting = current_user()
    target = _scope_query(User.query, acting).filter_by(id=user_id).first()
    if not target:
        return jsonify({"error": "User not found."}), 404
    if target.id == acting.id:
        return (
            jsonify({"error": "You can't delete your own account while logged in."}),
            400,
        )

    db.session.delete(target)
    db.session.commit()
    return jsonify({"message": "User deleted."}), 200
