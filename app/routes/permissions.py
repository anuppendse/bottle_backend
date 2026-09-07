from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import Permission, RolePermission, ROLES, default_permissions_for_role

SETUP_KEY = "setup"  # never assignable — Admin-only via require_permission's own check

from app.decorators import require_permission

permissions_bp = Blueprint("permissions", __name__)


@permissions_bp.get("")
@require_permission("users")
def get_permission_tree():
    """Returns the assignable permission tree (with parent/child nesting)
    plus the always-locked entries (currently just 'setup'), read live
    from the Permission table — not a hardcoded list."""
    rows = Permission.query.order_by(Permission.sort_order, Permission.key).all()
    parents = [p for p in rows if not p.parent_key and p.key != SETUP_KEY]
    tree = []
    for p in parents:
        children = [c.to_dict() for c in rows if c.parent_key == p.key]
        node = {"key": p.key, "label": p.label}
        if children:
            node["children"] = children
        tree.append(node)
    locked = [p.to_dict() for p in rows if p.key == SETUP_KEY]
    return jsonify({"tree": tree, "locked": locked, "roles": ROLES})


@permissions_bp.get("/role-defaults")
@require_permission("users")
def role_defaults():
    """Resolves the default permission set for a role."""
    role = request.args.get("role", "")
    return jsonify({"role": role, "permissions": default_permissions_for_role(role)})


@permissions_bp.put("/role-defaults")
@require_permission("users")
def set_role_defaults():
    """Lets an Admin configure a role's default permission set,
    stored as rows in role_permissions rather than a fixed Python dict."""
    data = request.get_json(silent=True) or {}
    role = (data.get("role") or "").strip()
    if role not in ROLES:
        return jsonify({"error": f"role must be one of: {', '.join(ROLES)}."}), 400

    keys = data.get("permissions") or []

    valid_perms = Permission.query.filter(
        Permission.key.in_(keys), Permission.key != SETUP_KEY
    ).all()

    RolePermission.query.filter_by(role=role).delete()
    for p in valid_perms:
        db.session.add(RolePermission(role=role, permission_id=p.id, granted=True))
    db.session.commit()

    return jsonify({"role": role, "permissions": sorted(p.key for p in valid_perms)})