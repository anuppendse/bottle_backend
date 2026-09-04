from flask import Blueprint, jsonify

from app.models import Recall, normalize_role
from app.decorators import require_permission, current_user

recalls_bp = Blueprint("recalls", __name__)


@recalls_bp.get("")
@require_permission("recalls")
def list_recalls():
    user = current_user()
    q = Recall.query
    if normalize_role(user.role) == "manufacturer":
        q = q.join(Recall.batch).filter_by(manufacturer_id=user.manufacturer_id)
    rows = q.order_by(Recall.recalled_at.desc()).all()
    return jsonify([r.to_dict() for r in rows])
