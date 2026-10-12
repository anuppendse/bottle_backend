from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token

from app.models import User, db, RecordStatus, Manufacturer
from app.decorators import require_auth, current_user
from sqlalchemy import or_

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return (
            jsonify({"error": "Enter your email and password to continue."}),
            400,
        )

    email = email.strip().lower()

    conditions = [
        User.email.ilike(email),
        User.username.ilike(email),
    ]

    user = User.query.filter(
        or_(*conditions),
        User.status == RecordStatus.ACTIVE,
    ).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid username/email or password."}), 401

    token = create_access_token(identity=user.id)
    return jsonify({"accessToken": token, "user": user.to_dict()})

@auth_bp.get("/me")
@require_auth
def me():
    return jsonify(current_user().to_dict())

@auth_bp.get("/account")
@require_auth
def account():
    user = current_user()

    manufacturer_name = None
    if user.manufacturer_id:
        m = Manufacturer.query.get(user.manufacturer_id)
        manufacturer_name = m.name if m else None

    role = user.role.value if hasattr(user.role, "value") else user.role

    return jsonify({
        "name": user.name,
        "email": user.email,
        "username": user.username,
        "manufacturer": manufacturer_name,   # None for Admin users
        "role": role,
    })
