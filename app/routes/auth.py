from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token

from app.models import User, db, RecordStatus
from app.decorators import require_auth, current_user
from sqlalchemy import or_

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    # Accept either key from the frontend, and trim/lowercase it
    email = data.get("email")
    password = data.get("password")
    
    print(data)

    if not email or not password:
        return (
            jsonify(
                {"error": "Enter your  email and password to continue."}
            ),
            400,
        )

    if email:
        email = email.strip().lower()

    conditions = []
    if email:
        conditions.append(User.email.ilike(email))
        conditions.append(User.username.ilike(email))

    user = User.query.filter(
        or_(*conditions),
        User.status == RecordStatus.ACTIVE,
    ).first()

    user.set_password(password)
    db.session.commit()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid username/email or password."}), 401

    token = create_access_token(identity=user.id)
    return jsonify({"accessToken": token, "user": user.to_dict()})


@auth_bp.get("/me")
@require_auth
def me():
    return jsonify(current_user().to_dict())
