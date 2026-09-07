from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import Manufacturer, gen_uuid, CODE_TYPES, CodeType, GENERATION_LEVELS,GenerationLevel
from app.decorators import require_role

manufacturer_bp = Blueprint("manufacturer", __name__)


@manufacturer_bp.get("")
@require_role("admin")
def list_manufacturers():
    rows = Manufacturer.query.order_by(Manufacturer.name).all()
    return jsonify([m.to_dict() for m in rows])


@manufacturer_bp.get("/<manufacturer_id>")
@require_role("admin")
def get_manufacturer(manufacturer_id):
    m = Manufacturer.query.get(manufacturer_id)
    if not m:
        return jsonify({"error": "Manufacturer not found."}), 404
    return jsonify(m.to_dict())


@manufacturer_bp.post("")
@require_role("admin")
def create_manufacturer():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    code_type = data.get("codeType")

    if not code_type:
        return jsonify({"error": "code_type is required."}), 400
    try:
        code_type = CodeType(code_type.strip().upper())

    except ValueError:
        return (
            jsonify({"error": f"Invalid code_type: {code_type}"}),
            400,
        )

    generation_level = data.get("generationlevel")
        

    if not generation_level:
        return jsonify({"error": "generation_level is required."}), 400
    try:
        generation_level = GenerationLevel(generation_level.strip().upper())

    except ValueError:
        return (
            jsonify({"error": f"Invalid generation_level: {generation_level}"}),
            400,
        )
    

    if not name:
        
        return jsonify({"error": "Manufacturer name is required."}), 400
    
    if Manufacturer.query.filter_by(db.func.lower(name)==name.lower()).first():
        return jsonify({"error": "A manufacturer with this name already exists."}), 400

    m = Manufacturer(
        name=name, code_type=code_type, generation_level=generation_level
    )
    db.session.add(m)
    db.session.commit()
    return jsonify(m.to_dict()), 201


@manufacturer_bp.put("/<manufacturer_id>")
@require_role("admin")
def update_manufacturer(manufacturer_id):
    m = Manufacturer.query.get(manufacturer_id)
    if not m:
        return jsonify({"error": "Manufacturer not found."}), 404

    data = request.get_json(silent=True) or {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Manufacturer name cannot be empty."}), 400
        m.name = name
    if "codeType" in data:
        code_type = (data.get("codeType") or "").strip()
        if code_type not in CODE_TYPES:
            return (
                jsonify(
                    {"error": f"codeType must be one of: {', '.join(CODE_TYPES)}."}
                ),
                400,
            )
        m.code_type = code_type
    if "generationLevel" in data:
        generation_level = (data.get("generationLevel") or "").strip().lower()
        if generation_level not in GENERATION_LEVELS:
            return (
                jsonify(
                    {
                        "error": f"generationLevel must be one of: {', '.join(GENERATION_LEVELS)}."
                    }
                ),
                400,
            )
        m.generation_level = generation_level

    db.session.commit()
    return jsonify(m.to_dict())


@manufacturer_bp.delete("/<manufacturer_id>")
@require_role("admin")
def delete_manufacturer(manufacturer_id):
    m = Manufacturer.query.get(manufacturer_id)
    if not m:
        return jsonify({"error": "Manufacturer not found."}), 404
    if m.products or m.users:
        return (
            jsonify(
                {
                    "error": "Cannot delete a manufacturer with existing products or users."
                }
            ),
            400,
        )
    db.session.delete(m)
    db.session.commit()
    return jsonify({"deleted": manufacturer_id})
