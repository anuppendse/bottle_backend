from flask import Blueprint, request, jsonify
from sqlalchemy import func

from app.extensions import db
from app.models import (
    Permission,
    RolePermission,
    UserPermission,
    ROLES,
    default_permissions_for_role,
    User,
)

SETUP_KEY = "setup"  # never assignable — Admin-only via require_permission's own check

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
                    UserPermission.user_id == user_id).all()
        
        for up in user_permissions:
            user_permission_dict[up.role_permission_id] = up.granted
        

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
            print("parent_role_node", parent_role_node)
            parent_node_dict = {}
            parent_node_dict["key"] = parent_row.key
            parent_node_dict["label"] = parent_row.label
            parent_node_dict["parent_id"] = parent_row.parent_id
            parent_node_dict["granted"] = parent_role_node.granted
            parent_node_dict["id"] = parent_role_node.id
            if user_id:
                parent_node_dict["granted"] = user_permission_dict.get(parent_role_node.id)
                
            parent_node_dict["permission_id"] = parent_row.id
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
                print("child_role_node", child_role_node)
                child_node_dict = {}
                child_node_dict["key"] = child_row.key
                child_node_dict["label"] = child_row.label
                child_node_dict["parent_id"] = child_row.parent_id
                child_node_dict["granted"] = child_role_node.granted
                child_node_dict["id"] = child_role_node.id
                if user_id:
                    child_node_dict["granted"] = user_permission_dict.get(child_role_node.id)
                child_node_dict["permission_id"] = child_row.id
                if child_role_node.role.value in all_permission_dict:
                    all_permission_dict.get(child_role_node.role.value).append(
                        child_node_dict
                    )
                else:
                    node_list = []
                    node_list.append(child_node_dict)
                    all_permission_dict[child_role_node.role.value] = node_list
                    
    if user_id:
        return jsonify({"user_parmissions" : all_permission_dict[user.role.value]}), 200
    return jsonify(all_permission_dict), 200



@permissions_bp.get("/user")
def get_user_permission_tree():

    parent_rows = (
        Permission.query.filter(Permission.parent_id.is_(None))
        .order_by(Permission.sort_order)
        .all()
    )

    all_permission_dict = {}
    for parent_row in parent_rows:
        parent_user_nodes = UserPermission.query.filter(
            UserPermission.permission_id == parent_row.to_dict().get("id")
        ).all()

        for parent_user_node in parent_user_nodes:
            parent_node_dict = {}
            parent_node_dict["key"] = parent_row.key
            parent_node_dict["label"] = parent_row.label
            parent_node_dict["parent_id"] = parent_row.parent_id
            parent_node_dict["granted"] = parent_user_node.granted
            parent_node_dict["id"] = parent_row.id
            parent_node_dict["permission_id"] = parent_row.id
            if parent_user_node.user_id in all_permission_dict:
                all_permission_dict.get(parent_user_node.user_id).append(
                    parent_node_dict
                )
            else:
                node_list = []
                node_list.append(parent_node_dict)
                all_permission_dict[parent_user_node.user_id] = node_list

        children = Permission.query.filter(
            Permission.parent_id == parent_row.to_dict().get("id")
        ).all()
        for child_row in children:
            child_user_nodes = UserPermission.query.filter(
                UserPermission.permission_id == child_row.to_dict().get("id")
            ).all()

            for child_user_node in child_user_nodes:
                child_node_dict = {}
                child_node_dict["key"] = child_row.key
                child_node_dict["label"] = child_row.label
                child_node_dict["parent_id"] = child_row.parent_id
                child_node_dict["granted"] = child_user_node.granted
                child_node_dict["id"] = child_row.id
                child_node_dict["permission_id"] = child_row.id
                if child_user_node.user_id in all_permission_dict:
                    all_permission_dict.get(child_user_node.user_id).append(
                        child_node_dict
                    )
                else:
                    node_list = []
                    node_list.append(child_node_dict)
                    all_permission_dict[child_user_node.user_id] = node_list
    return jsonify(all_permission_dict), 200


@permissions_bp.get("/role-defaults")
@require_permission("users")
def role_defaults():
    """Resolves the default permission set for a role."""
    role = request.args.get("role", "")
    return jsonify({"role": role, "permissions": default_permissions_for_role(role)})


# ------------------------------------------------------------------------------------------------
#                            PATCH API
# ------------------------------------------------------------------------------------------------
@permissions_bp.patch("/role-defaults")
@require_permission("users")
def add_role_permissions():
    """Grants the given permissions to a role, without touching any
    existing permissions that aren't mentioned in the request."""
    data = request.get_json(silent=True) or {}
    role = (data.get("role") or "").strip()
    if role not in ROLES:
        return jsonify({"error": f"role must be one of: {', '.join(ROLES)}."}), 400

    keys = data.get("permissions") or []

    valid_perms = Permission.query.filter(
        Permission.key.in_(keys), Permission.key != SETUP_KEY
    ).all()

    existing_rows = RolePermission.query.filter_by(role=role).all()
    existing_by_perm_id = {rp.permission_id: rp for rp in existing_rows}

    for p in valid_perms:
        rp = existing_by_perm_id.get(p.id)
        if rp:
            rp.granted = True  # already exists, make sure it's on
        else:
            db.session.add(RolePermission(role=role, permission_id=p.id, granted=True))

    db.session.commit()

    all_rows = RolePermission.query.filter_by(role=role, granted=True).all()
    perm_keys = [
        p.key
        for p in Permission.query.filter(
            Permission.id.in_([rp.permission_id for rp in all_rows])
        ).all()
    ]

    return jsonify({"role": role, "permissions": sorted(perm_keys)})


# --------------------------------------------------------------------------------------------
#                    DELETE API
# -------------------------------------------------------------------------------------------
@permissions_bp.delete("/role-defaults")
@require_permission("users")
def remove_role_permissions():
    """Revokes the given permissions from a role. Only touches the
    permissions sent in the request — everything else stays as is."""
    data = request.get_json(silent=True) or {}
    role = (data.get("role") or "").strip()
    if role not in ROLES:
        return jsonify({"error": f"role must be one of: {', '.join(ROLES)}."}), 400

    keys = data.get("permissions") or []

    valid_perms = Permission.query.filter(Permission.key.in_(keys)).all()
    valid_perm_ids = [p.id for p in valid_perms]

    rows_to_remove = RolePermission.query.filter(
        RolePermission.role == role,
        RolePermission.permission_id.in_(valid_perm_ids),
    ).all()

    for rp in rows_to_remove:
        still_referenced = UserPermission.query.filter_by(
            role_permission_id=rp.id
        ).first()
        if still_referenced:
            rp.granted = False  # can't delete, so just turn it off
        else:
            db.session.delete(rp)

    db.session.commit()

    remaining_rows = RolePermission.query.filter_by(role=role, granted=True).all()
    remaining_keys = [
        p.key
        for p in Permission.query.filter(
            Permission.id.in_([rp.permission_id for rp in remaining_rows])
        ).all()
    ]

    return jsonify({"role": role, "permissions": sorted(remaining_keys)})


# -----------------------------------------------------------------------------------------------
#                              GET USER PERMISSION
# -----------------------------------------------------------------------------------------------


@permissions_bp.get("/user-defaults")
@require_permission("users")
def user_defaults():
    """Resolves the effective permission set for a single user:
    starts from their role's defaults, then applies any personal
    overrides on top."""
    user_id = request.args.get("user_id", "")

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "user not found"}), 404

    # start with the role's default permission IDs
    effective_ids = set(default_permissions_for_role(user.role.value))

    # apply this user's personal overrides on top
    overrides = UserPermission.query.filter_by(user_id=user_id).all()
    for up in overrides:
        if up.granted:
            effective_ids.add(up.permission_id)
        else:
            effective_ids.discard(up.permission_id)

    # convert IDs to readable keys for the response
    perms = Permission.query.filter(Permission.id.in_(effective_ids)).all()

    return jsonify(
        {
            "user_id": user_id,
            "role": user.role.value if hasattr(user.role, "value") else user.role,
            "permissions": sorted(p.key for p in perms),
        }
    )

    # -----------------------------------------------------------------------------------------
    #                                 PATCH API
    # -----------------------------------------------------------------------------------------


@permissions_bp.patch("/user-overrides")
@require_permission("users")
def set_user_permission_overrides():
    """Sets an explicit override for a user on top of their role's defaults.
    Only touches the permissions sent in the request."""
    data = request.get_json(silent=True) or {}
    user_id = (data.get("user_id") or "").strip()
    keys = data.get("permissions") or []
    granted = data.get("granted", True)  # allows explicit grant or deny

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "user not found"}), 404

    valid_perms = Permission.query.filter(
        func.lower(Permission.key).in_([k.lower() for k in keys])
    ).all()

    existing_rows = UserPermission.query.filter_by(user_id=user_id).all()
    existing_by_perm_id = {up.permission_id: up for up in existing_rows}

    skipped = []
    for p in valid_perms:
        role_perm = RolePermission.query.filter_by(
            role=user.role, permission_id=p.id
        ).first()
        if not role_perm:
            skipped.append(p.key)  # no matching role_permission row to link to
            continue

        up = existing_by_perm_id.get(p.id)
        if up:
            up.granted = granted
        else:
            db.session.add(
                UserPermission(
                    user_id=user_id,
                    permission_id=p.id,
                    role_permission_id=role_perm.id,
                    granted=granted,
                )
            )

    db.session.commit()

    remaining = UserPermission.query.filter_by(user_id=user_id, granted=True).all()
    perm_keys = [
        p.key
        for p in Permission.query.filter(
            Permission.id.in_([up.permission_id for up in remaining])
        ).all()
    ]

    resp = {"user_id": user_id, "permissions": sorted(perm_keys)}
    if skipped:
        resp["skipped"] = skipped
    return jsonify(resp)


# ---------------------------------------------------------------------------------------------
#                             DELETE API
# ---------------------------------------------------------------------------------------------


@permissions_bp.delete("/user-overrides")
@require_permission("users")
def remove_user_permission_overrides():
    """Soft-deletes a user's override for the given permissions by
    setting granted=False. The row stays in the table (not hard-deleted),
    but is treated the same as an explicit deny."""
    data = request.get_json(silent=True) or {}
    user_id = (data.get("user_id") or "").strip()
    keys = data.get("permissions") or []

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "user not found"}), 404

    valid_perms = Permission.query.filter(
        func.lower(Permission.key).in_([k.lower() for k in keys])
    ).all()
    valid_perm_ids = [p.id for p in valid_perms]

    rows_to_remove = UserPermission.query.filter(
        UserPermission.user_id == user_id,
        UserPermission.permission_id.in_(valid_perm_ids),
    ).all()

    for up in rows_to_remove:
        up.granted = False  # soft delete — row stays, just marked not granted

    db.session.commit()

    remaining = UserPermission.query.filter_by(user_id=user_id, granted=True).all()
    perm_keys = [
        p.key
        for p in Permission.query.filter(
            Permission.id.in_([up.permission_id for up in remaining])
        ).all()
    ]

    return jsonify({"user_id": user_id, "permissions": sorted(perm_keys)})
