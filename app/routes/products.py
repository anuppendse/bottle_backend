from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import Product, Manufacturer, Category, normalize_role, RecordStatus
from app.decorators import require_permission, current_user

products_bp = Blueprint("products", __name__)


def _scope_query(q, user):
    if normalize_role(user.role) == "manufacturer":
        return q.filter_by(manufacturer_id=user.manufacturer_id)
    return q


@products_bp.get("")
@require_permission("products")
def list_products():
    user = current_user()
    rows = Product.query.order_by(Product.updated_at.desc()).all()
    return jsonify([p.to_dict() for p in rows])


@products_bp.get("/<product_id>")
@require_permission("products")
def get_product(product_id):
    user = current_user()
    p = _scope_query(Product.query, user).filter_by(id=product_id).first()
    if not p:
        return jsonify({"error": "Product not found."}), 404
    return jsonify(p.to_dict())


@products_bp.post("")
@require_permission("products")
def create_product():
    user = current_user()
    if normalize_role(user.role) == "employee":
        return jsonify({"error": "View-only access to the product catalog."}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Product name is required."}), 400

    category = Category.query.get(data.get("categoryId"))
    if not category:
        return jsonify({"error": "A valid categoryId is required."}), 400

    shelf_life_months = data.get("shelfLifeMonths")
    if not shelf_life_months or int(shelf_life_months) <= 0:
        return jsonify({"error": "shelfLifeMonths is required and must be a positive number."}), 400

    manufacturer_id = user.manufacturer_id if normalize_role(user.role) == "manufacturer" else data.get("manufacturerId")
    manufacturer = Manufacturer.query.get(manufacturer_id) if manufacturer_id else None
    if not manufacturer:
        return jsonify({"error": "A valid manufacturer is required."}), 400

    product = Product(
        name=name,
        category_id=category.id,
        manufacturer_id=manufacturer.id,
        description=data.get("desc", ""),
        shelf_life_months=int(shelf_life_months),
        status=RecordStatus.ACTIVE,
    )
    db.session.add(product)
    db.session.commit()
    return jsonify(product.to_dict()), 201


@products_bp.put("/<product_id>")
@require_permission("products")
def update_product(product_id):
    user = current_user()
    if normalize_role(user.role) == "employee":
        return jsonify({"error": "View-only access to the product catalog."}), 403
    p = _scope_query(Product.query, user).filter_by(id=product_id).first()
    if not p:
        return jsonify({"error": "Product not found."}), 404

    data = request.get_json(silent=True) or {}
    if "name" in data:
        p.name = data["name"] or p.name
    if "categoryId" in data:
        category = Category.query.get(data["categoryId"])
        if not category:
            return jsonify({"error": "A valid categoryId is required."}), 400
        p.category_id = category.id
    if "desc" in data:
        p.description = data["desc"]
    if "shelfLifeMonths" in data:
        if not data["shelfLifeMonths"] or int(data["shelfLifeMonths"]) <= 0:
            return jsonify({"error": "shelfLifeMonths must be a positive number."}), 400
        p.shelf_life_months = int(data["shelfLifeMonths"])

    db.session.commit()
    return jsonify(p.to_dict())

@products_bp.patch("/<product_id>/status")
@require_permission("products")
def set_product_status(product_id):
    user = current_user()
    if normalize_role(user.role) == "employee":
        return jsonify({"error": "View-only access to the product catalog."}), 403

    p = _scope_query(Product.query, user).filter_by(id=product_id).first()
    if not p:
        return jsonify({"error": "Product not found."}), 404

    data = request.get_json(silent=True) or {}
    new_status = (data.get("status") or "").strip().upper()
    if new_status not in (RecordStatus.ACTIVE.value, RecordStatus.INACTIVE.value):
        return jsonify({"error": "status must be ACTIVE or INACTIVE."}), 400

    p.status = RecordStatus(new_status)
    db.session.commit()
    return jsonify(p.to_dict())
