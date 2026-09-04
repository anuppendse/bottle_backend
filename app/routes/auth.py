from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token

from app.models import User, db
from app.decorators import require_auth, current_user

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Enter your email and password to continue."}), 400

    user = User.query.filter(User.email.ilike(email)).first()
    user.set_password(password)
    db.session.commit()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password."}), 401
    if user.status == "Inactive":
        return jsonify({"error": "This account is inactive. Contact your Admin."}), 403

    token = create_access_token(identity=user.id)
    return jsonify({"accessToken": token, "user": user.to_dict()})


@auth_bp.get("/me")
@require_auth
def me():
    return jsonify(current_user().to_dict())
