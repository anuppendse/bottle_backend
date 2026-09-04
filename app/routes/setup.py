from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import SystemSetup, Manufacturer
from app.decorators import require_permission

setup_bp = Blueprint("setup", __name__)


def _get_or_create(manufacturer_id):
    setup = SystemSetup.query.get(manufacturer_id)
    if not setup:
        setup = SystemSetup(manufacturer_id=manufacturer_id)
        db.session.add(setup)
        db.session.commit()
    return setup


@setup_bp.get("/manufacturers")
@require_permission("setup")
def list_manufacturers():
    """Lets the Setup screen offer a manufacturer picker, since defaults
    and company profile are now stored per manufacturer rather than as
    a single global row."""
    rows = Manufacturer.query.order_by(Manufacturer.name).all()
    return jsonify([m.to_dict() for m in rows])


@setup_bp.get("")
@require_permission("setup")
def get_setup():
    manufacturer_id = request.args.get("manufacturerId")
    if not manufacturer_id:
        return jsonify({"error": "manufacturerId is required."}), 400
    if not Manufacturer.query.get(manufacturer_id):
        return jsonify({"error": "Manufacturer not found."}), 404
    return jsonify(_get_or_create(manufacturer_id).to_dict())


@setup_bp.put("")
@require_permission("setup")
def update_setup():
    data = request.get_json(silent=True) or {}
    manufacturer_id = data.get("manufacturerId") or request.args.get("manufacturerId")
    if not manufacturer_id:
        return jsonify({"error": "manufacturerId is required."}), 400
    if not Manufacturer.query.get(manufacturer_id):
        return jsonify({"error": "Manufacturer not found."}), 404

    setup = _get_or_create(manufacturer_id)
    for field in ("defaultCodeType", "defaultGenerationLevel", "companyName",
                  "gstin", "contactEmail", "contactPhone"):
        if field in data:
            snake = "".join("_" + c.lower() if c.isupper() else c for c in field).lstrip("_")
            setattr(setup, snake, data[field])
    db.session.commit()
    return jsonify(setup.to_dict())
