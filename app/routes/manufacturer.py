from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import Manufacturer, CodeType, GenerationLevel
from app.decorators import require_permission

manufacturers_bp = Blueprint("manufacturers", __name__)


def _apply_optional_fields(m, data):
    if "companyName" in data:
        m.company_name = data["companyName"]
    if "gstin" in data:
        m.gstin = data["gstin"]
    if "contactEmail" in data:
        m.contact_email = data["contactEmail"]
    if "contactPhone" in data:
        m.contact_phone = data["contactPhone"]


@manufacturers_bp.get("")
@require_permission("manufacturers")
def list_manufacturers():
    rows = Manufacturer.query.order_by(Manufacturer.name).all()
    return jsonify([m.to_dict() for m in rows])


@manufacturers_bp.get("/<manufacturer_id>")
@require_permission("manufacturers")
def get_manufacturer(manufacturer_id):
    m = Manufacturer.query.get(manufacturer_id)
    if not m:
        return jsonify({"error": "Manufacturer not found."}), 404
    return jsonify(m.to_dict())


@manufacturers_bp.post("")
@require_permission("manufacturers")
def create_manufacturer():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Manufacturer name is required."}), 400
    if Manufacturer.query.filter(Manufacturer.name.ilike(name)).first():
        return jsonify({"error": "A manufacturer with that name already exists."}), 409

    code_type = data.get("codeType")
    generation_level = data.get("generationLevel")
    try:
        code_type_enum = CodeType(code_type) if code_type else CodeType.BOTH
        generation_level_enum = GenerationLevel(generation_level) if generation_level else GenerationLevel.UNIT
    except ValueError:
        return jsonify({"error": "Invalid codeType or generationLevel."}), 400

    m = Manufacturer(name=name, code_type=code_type_enum, generation_level=generation_level_enum)
    _apply_optional_fields(m, data)
    db.session.add(m)
    db.session.commit()
    return jsonify(m.to_dict()), 201


@manufacturers_bp.put("/<manufacturer_id>")
@require_permission("manufacturers")
def update_manufacturer(manufacturer_id):
    m = Manufacturer.query.get(manufacturer_id)
    if not m:
        return jsonify({"error": "Manufacturer not found."}), 404

    data = request.get_json(silent=True) or {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Manufacturer name is required."}), 400
        if Manufacturer.query.filter(Manufacturer.name.ilike(name), Manufacturer.id != manufacturer_id).first():
            return jsonify({"error": "A manufacturer with that name already exists."}), 409
        m.name = name

    if "codeType" in data:
        try:
            m.code_type = CodeType(data["codeType"])
        except ValueError:
            return jsonify({"error": "Invalid codeType."}), 400
    if "generationLevel" in data:
        try:
            m.generation_level = GenerationLevel(data["generationLevel"])
        except ValueError:
            return jsonify({"error": "Invalid generationLevel."}), 400

    _apply_optional_fields(m, data)
    db.session.commit()
    return jsonify(m.to_dict())


@manufacturers_bp.delete("/<manufacturer_id>")
@require_permission("manufacturers")
def delete_manufacturer(manufacturer_id):
    m = Manufacturer.query.get(manufacturer_id)
    if not m:
        return jsonify({"error": "Manufacturer not found."}), 404
    if m.products:
        return jsonify({"error": f"{len(m.products)} product(s) still belong to this manufacturer — reassign or remove them first."}), 409
    if m.users:
        return jsonify({"error": f"{len(m.users)} user(s) still belong to this manufacturer — reassign or remove them first."}), 409

    db.session.delete(m)
    db.session.commit()
    return jsonify({"deleted": manufacturer_id})