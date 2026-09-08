from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import Category, RecordStatus, normalize_role
from app.decorators import require_permission, current_user

categories_bp = Blueprint("categories", __name__)


@categories_bp.get("")
@require_permission("products")
def list_categories():
    """Returns every category (Active and Inactive) so the management
    page can show and reactivate inactive ones — the Product form's
    dropdown should filter to status == "ACTIVE" client-side."""
    rows = Category.query.order_by(Category.name).all()
    return jsonify([c.to_dict() for c in rows])


@categories_bp.post("")
@require_permission("products")
def create_category():
    user = current_user()
    if normalize_role(user.role) == "employee":
        return jsonify({"error": "View-only access to the product catalog."}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Category name is required."}), 400
    if Category.query.filter(Category.name.ilike(name)).first():
        return jsonify({"error": "A category with that name already exists."}), 409

    category = Category(name=name, status=RecordStatus.ACTIVE)
    db.session.add(category)
    db.session.commit()
    return jsonify(category.to_dict()), 201


@categories_bp.put("/<category_id>")
@require_permission("products")
def update_category(category_id):
    user = current_user()
    if normalize_role(user.role) == "employee":
        return jsonify({"error": "View-only access to the product catalog."}), 403
    category = Category.query.get(category_id)
    if not category:
        return jsonify({"error": "Category not found."}), 404

    data = request.get_json(silent=True) or {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Category name is required."}), 400
        if Category.query.filter(Category.name.ilike(name), Category.id != category_id).first():
            return jsonify({"error": "A category with that name already exists."}), 409
        category.name = name

    db.session.commit()
    return jsonify(category.to_dict())


@categories_bp.post("/<category_id>/toggle-status")
@require_permission("products")
def toggle_category_status(category_id):
    """Soft activate/deactivate — flips RecordStatus, keeps the row (and
    any products still pointing at it) intact. This is the everyday
    "remove from use" action; DELETE below is the separate, harder
    "actually remove it" action for genuinely unused categories."""
    user = current_user()
    if normalize_role(user.role) == "employee":
        return jsonify({"error": "View-only access to the product catalog."}), 403
    category = Category.query.get(category_id)
    if not category:
        return jsonify({"error": "Category not found."}), 404

    category.status = (
        RecordStatus.INACTIVE if category.status == RecordStatus.ACTIVE else RecordStatus.ACTIVE
    )
    db.session.commit()
    return jsonify(category.to_dict())


@categories_bp.delete("/<category_id>")
@require_permission("products")
def delete_category(category_id):
    """Hard delete — only allowed when no products reference this
    category (regardless of the category's own status). For simply
    hiding a category from new product assignments without losing
    history, use toggle-status instead."""
    user = current_user()
    if normalize_role(user.role) == "employee":
        return jsonify({"error": "View-only access to the product catalog."}), 403
    category = Category.query.get(category_id)
    if not category:
        return jsonify({"error": "Category not found."}), 404
    if category.products:
        return jsonify({"error": f"{len(category.products)} product(s) still use this category — reassign them first."}), 409

    db.session.delete(category)
    db.session.commit()
    return jsonify({"deleted": category_id})
