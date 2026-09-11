from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import Permission, RolePermission, ROLES, default_permissions_for_role

SETUP_KEY = "setup"  # never assignable — Admin-only via require_permission's own check

from app.decorators import require_permission

permissions_bp = Blueprint("permissions", __name__)


@permissions_bp.get("")
def get_permission_tree():
    parent_rows = (
        Permission.query.filter(Permission.parent_id.is_(None))
        .order_by(Permission.sort_order)
        .all()
    )

    all_permission_dict = {}
    for parent_row in parent_rows:
        parent_role_nodes = RolePermission.query.filter(
            RolePermission.permission_id == parent_row.to_dict().get("id")
        ).all()

        for parent_role_node in parent_role_nodes:
            parent_node_dict = {}
            parent_node_dict["key"] = parent_row.key
            parent_node_dict["label"] = parent_row.label
            parent_node_dict["parent_id"] = parent_row.parent_id
            parent_node_dict["granted"] = parent_role_node.granted
            if parent_role_node.role.value in all_permission_dict:
                all_permission_dict.get(parent_role_node.role.value).append(
                    parent_node_dict
                )
            else:
                node_list = []
                node_list.append(parent_node_dict)
                all_permission_dict[parent_role_node.role.value] = node_list

        children = Permission.query.filter(
            Permission.parent_id == parent_row.to_dict().get("id")
        ).all()
        for child_row in children:
            child_role_nodes = RolePermission.query.filter(
                RolePermission.permission_id == child_row.to_dict().get("id")
            ).all()

            for child_role_node in child_role_nodes:
                child_node_dict = {}
                child_node_dict["key"] = child_row.key
                child_node_dict["label"] = child_row.label
                child_node_dict["parent_id"] = child_row.parent_id
                child_node_dict["granted"] = child_role_node.granted
                if child_role_node.role.value in all_permission_dict:
                    all_permission_dict.get(child_role_node.role.value).append(
                        child_node_dict
                    )
                else:
                    node_list = []
                    node_list.append(child_node_dict)
                    all_permission_dict[child_role_node.role.value] = node_list
    return jsonify(all_permission_dict), 200


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
