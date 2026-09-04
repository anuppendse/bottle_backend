from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import Category, normalize_role
from app.decorators import require_permission, current_user

categories_bp = Blueprint("categories", __name__)


@categories_bp.get("")
@require_permission("products")
def list_categories():
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

    category = Category(name=name)
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
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Category name is required."}), 400
    if Category.query.filter(Category.name.ilike(name), Category.id != category_id).first():
        return jsonify({"error": "A category with that name already exists."}), 409

    category.name = name
    db.session.commit()
    return jsonify(category.to_dict())


@categories_bp.delete("/<category_id>")
@require_permission("products")
def delete_category(category_id):
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
