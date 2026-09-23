from flask import Blueprint, request, jsonify
from sqlalchemy import func

from app.extensions import db
from app.models import (
    Permission,
    RolePermission,
    UserPermission,
    Role,
    default_permissions_for_role,
    User,
)

from app.decorators import require_permission

permissions_bp = Blueprint("permissions", __name__)


@permissions_bp.get("")
def get_permission_tree():

    user_id = request.args.get("user_id", "")

    user_permission_dict = {}
    if user_id:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "user not found"}), 404

        user_permissions = UserPermission.query.filter(
            UserPermission.user_id == user_id
        ).all()

        for up in user_permissions:
            user_permission_dict[up.role_permission_id] = up

    # Walk ALL permissions regardless of nesting depth (was: parent_rows
    # loop + a separate one-level-deep children loop below it — same body
    # duplicated twice, and anything nested past depth 2 was never visited).
    all_rows = Permission.query.order_by(Permission.sort_order).all()

    all_permission_dict = {}
    for perm_row in all_rows:
        role_nodes = RolePermission.query.filter(
            RolePermission.permission_id == perm_row.id
        ).all()

        for role_node in role_nodes:
            # Same fields as parent_node_dict / child_node_dict before.
            node_dict = {
                "key": perm_row.key,
                "label": perm_row.label,
                "parent_id": perm_row.parent_id,
                "granted": role_node.granted,
                "id": role_node.id,
                "permission_id": perm_row.id,
            }

            if user_id:
                up = user_permission_dict.get(role_node.id)
                if up:
                    node_dict["granted"] = up.granted
                    node_dict["user_id"] = user_id
                    node_dict["id"] = up.id
                    node_dict["role_permission_id"] = role_node.id

            all_permission_dict.setdefault(role_node.role.value, []).append(node_dict)

    if user_id:
        return (
            jsonify({"user_permissions": all_permission_dict.get(user.role.value, [])}),
            200,
        )
    return jsonify(all_permission_dict), 200


# -------------------------------------PATCH API-------------------------------------------------
@permissions_bp.patch("/role-permissions")
def update_role_permission():

    data = request.get_json(silent=True) or {}

    role_permission_ids = data["role_permission_ids"]
    granted_perms = data["granted_perms"]

    if (
        not isinstance(role_permission_ids, list)
        or not isinstance(granted_perms, list)
        or len(role_permission_ids) != len(granted_perms)
    ):
        return jsonify({"error": "invalid data"}), 400

    if not all(isinstance(item, bool) for item in granted_perms):
        return jsonify({"error": "granted must be true or false"}), 400

    # Find RolePermission
    role_permissions = RolePermission.query.filter(
        RolePermission.id.in_(role_permission_ids)
    ).all()

    if not role_permissions or len(role_permissions) != len(role_permission_ids):
        return jsonify({"error": "Some Role permissions not found"}), 404

    role_permissions_dict = {
        role_permission.id: role_permission for role_permission in role_permissions
    }

    modified_role_permission_list = []
    modified_user_permission_list = []
    for i, role_permission_id in enumerate(role_permission_ids):
        role_permission_object = role_permissions_dict[role_permission_id]
        role_permission_object.granted = granted_perms[i]
        modified_role_permission_list.append(role_permission_object)

        user_permission_rows = UserPermission.query.filter_by(
            role_permission_id=role_permission_id
        ).all()
        for user_permission in user_permission_rows:
            user_permission.granted = granted_perms[i]
            modified_user_permission_list.append(user_permission)

    db.session.add_all(modified_role_permission_list)
    db.session.add_all(modified_user_permission_list)
    db.session.commit()

    return (
        jsonify(
            {
                "message": "Permission updated successfully",
                "role_permissions": [
                    rp.to_dict() for rp in modified_role_permission_list
                ],
            }
        ),
        200,
    )


@permissions_bp.post("/role-permissions")
@require_permission("users")
def create_role_permission():

    data = request.get_json(silent=True) or {}
    permission_id = data.get("id")

    if permission_id is None:
        return jsonify({"error": "id is required"}), 400

    permission = Permission.query.get(permission_id)
    if not permission:
        return jsonify({"error": f"no permission found for id '{permission_id}'"}), 404

    existing_rows = RolePermission.query.filter_by(permission_id=permission.id).all()
    existing_by_role = {rp.role.value: rp for rp in existing_rows}

    if len(existing_rows) == len(Role):
        return jsonify({"message": "This Permission have been given already"}), 409

    rp_list = []
    user_list = User.query.all()

    for role_value in Role:
        if role_value.value not in existing_by_role:
            rp = RolePermission(
                role=role_value, permission_id=permission.id, granted=False
            )
            db.session.add(rp)
            db.session.flush()

            existing_by_role[role_value.value] = rp

            rp_list.append(rp)
            user_permission_list = []
            for user in user_list:
                userPermission = UserPermission(
                    user_id=user.id,
                    role_permission_id=rp.id,
                    permission_id=rp.permission_id,
                    granted=rp.granted,
                )
                user_permission_list.append(userPermission)
            db.session.add_all(user_permission_list)
    db.session.commit()

    return (
        jsonify(
            {
                "rp": [{**rp.to_dict(), "key": permission.key} for rp in rp_list],
                "message": "Role permissions and user permissions created for all users",
            }
        ),
        201,
    )


@permissions_bp.patch("/user-permissions/<user_id>")
def update_user_permission(user_id):

    user = User.query.filter_by(id=user_id).first()
    if not user:
        return jsonify({"error": "User not found."}), 404

    data = request.get_json(silent=True) or {}

    user_permission_ids = data["user_permission_ids"]
    granted_perms = data["granted_perms"]

    if (
        not isinstance(user_permission_ids, list)
        or not isinstance(granted_perms, list)
        or len(user_permission_ids) != len(granted_perms)
    ):
        return jsonify({"error": "invalid data"}), 400

    if not all(isinstance(item, bool) for item in granted_perms):
        return jsonify({"error": "granted must be true or false"}), 400

    # Find RolePermission
    user_permissions = UserPermission.query.filter(
        UserPermission.id.in_(user_permission_ids)
    ).all()

    if not user_permissions or len(user_permissions) != len(user_permission_ids):
        return jsonify({"error": "Some User permissions not found"}), 404

    user_permissions_dict = {
        user_permission.id: user_permission for user_permission in user_permissions
    }

    modified_user_permission_list = []
    for i, user_permission_id in enumerate(user_permission_ids):
        user_permission_object = user_permissions_dict[user_permission_id]
        user_permission_object.granted = granted_perms[i]
        modified_user_permission_list.append(user_permission_object)
    db.session.add_all(modified_user_permission_list)
    db.session.commit()

    return (
        jsonify(
            {
                "message": "User permissions updated successfully",
                "user_permissions": [
                    rp.to_dict() for rp in modified_user_permission_list
                ],
            }
        ),
        200,
    )


# -----------------------API for Dropdown-----------------------------------------------
@permissions_bp.get("/keys")
@require_permission("users")
def get_permission_keys():
    """Feeds the dropdown: every assignable permission's id/key/label.
    'setup' is excluded — it's Admin-only and never assignable via a
    role_permissions row."""
    perms = Permission.query.order_by(Permission.sort_order).all()
    return jsonify([p.to_dict() for p in perms]), 200
