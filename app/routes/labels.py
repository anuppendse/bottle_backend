import csv
import io
import os
import json
from datetime import date


from flask import Blueprint, request, jsonify, Response, current_app, send_file

from app.extensions import db
from app.helpers import mint_code
from app.models import Batch, Product, Code, CsvExport, GENERATION_LEVELS, CODE_TYPES, normalize_role
from app.decorators import require_permission, current_user
from app.utils import add_months


labels_bp = Blueprint("labels", __name__)


@labels_bp.post("/generate")
@require_permission("labelGeneration")
def generate_labels():
    """Creates (or targets) a batch, resolves shelf life directly from
    the product, and mints codes according to the batch's generation
    level:
      - "batch": exactly ONE Code row is ever minted for the batch —
        the code represents the whole batch, not a physical unit.
      - "unit": one Code row per unit, up to `count` — tens of
        thousands of rows for a large batch.
    """
    user = current_user()
    data = request.get_json(silent=True) or {}

    product_name = (data.get("productName") or "").strip()
    product_id = data.get("productId")
    mrp = data.get("mrp")
    count = data.get("count")
    quantity = data.get("quantity")
    generation_level = (data.get("generationLevel") or "unit").strip().lower()
    code_type = (data.get("codeType") or "QR").strip()

    if not product_name and not product_id:
        return jsonify({"error": "Enter a product name to enable generation."}), 400
    if not mrp or not count or int(count) <= 0:
        return jsonify({"error": "Enter an MRP and a positive number of units to enable generation."}), 400
    if generation_level not in GENERATION_LEVELS:
        return jsonify({"error": f"generationLevel must be one of: {', '.join(GENERATION_LEVELS)}."}), 400
    if code_type not in CODE_TYPES:
        return jsonify({"error": f"codeType must be one of: {', '.join(CODE_TYPES)}."}), 400

    product = None
    if product_id:
        product = Product.query.get(product_id)
    if not product and product_name:
        q = Product.query.filter(Product.name.ilike(product_name))
        if normalize_role(user.role) == "manufacturer":
            q = q.filter_by(manufacturer_id=user.manufacturer_id)
        product = q.first()
    if not product:
        return jsonify({"error": "No matching product found. Create the product first."}), 404
    if normalize_role(user.role) == "manufacturer" and product.manufacturer_id != user.manufacturer_id:
        return jsonify({"error": "403 — that product belongs to a different manufacturer."}), 403

    mfg_date = date.today()
    expiry_date = add_months(mfg_date, product.shelf_life_months)
    count = int(count)

    batch_no = (data.get("batchNo") or "").strip() or None
    batch = Batch.query.get(batch_no) if batch_no else None
    if not batch:
        batch_kwargs = dict(
            product_id=product.id, manufacturer_id=product.manufacturer_id,
            mfg_date=mfg_date, expiry_date=expiry_date, qty=count, mrp=mrp,
            status="IN PRODUCTION", generation_level=generation_level, created_by=user.id,        )
        if batch_no:
            batch_kwargs["batch_no"] = batch_no
        batch = Batch(**batch_kwargs)
        db.session.add(batch)
    else:
        batch.qty += count  # generation_level is fixed at creation, not overridable on top-up

    db.session.flush()

    

    tokens = []
    if batch.generation_level == "batch":
        if not batch.codes:
            tokens = mint_code(batch, code_type)
        codes_generated = len(tokens)
    else:
        for i in range(count):
            tokens.extend(mint_code(batch, code_type))
        codes_generated = len(tokens)

    export = CsvExport(batch_no=batch.batch_no)
    db.session.add(export)
    db.session.commit()

    return jsonify({
        "batch": batch.to_dict(),
        "codesGenerated": codes_generated,
        "previewTokens": tokens[:3],
        "csvExportId": export.id,
    }), 201


@labels_bp.get("/<batch_no>/csv")
@require_permission("labelGeneration")
def download_batch_csv(batch_no):
    user = current_user()
    batch = Batch.query.get(batch_no)
    if not batch:
        return jsonify({"error": "Batch not found."}), 404
    if normalize_role(user.role) == "manufacturer" and batch.manufacturer_id != user.manufacturer_id:
        return jsonify({"error": "403 — access denied."}), 403

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["batchNumber", "token", "payload"])
    for c in batch.codes:
        writer.writerow([c.batch_no, c.token, json.dumps(c.payload)])
    return Response(
        buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={batch_no}-codes.csv"},
    )

@labels_bp.get("/codes/<token>/image")
@require_permission("labelGeneration")
def download_code_image(token):
    user = current_user()
    code = Code.query.filter_by(token=token).first()
    if not code:
        return jsonify({"error": "Code not found."}), 404
    if normalize_role(user.role) == "manufacturer" and code.batch.manufacturer_id != user.manufacturer_id:
        return jsonify({"error": "403 — access denied."}), 403

    fmt = request.args.get("type", "qr")
    path = (code.image_paths or {}).get(fmt)
    if not path or not os.path.exists(path):
        return jsonify({"error": f"No {fmt} image available for this code."}), 404
    return send_file(path, mimetype="image/png")