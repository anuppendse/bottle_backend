from datetime import date, datetime

from flask import Blueprint, jsonify

from app.extensions import db
from app.models import Code

verify_bp = Blueprint("verify", __name__)


@verify_bp.get("/<token>")
def verify_token(token):
    """Public product-genuineness check. Unrecognized codes never reveal
    product or batch details — mirrors the frontend's VerifyPage states:
    activated / firstScan / duplicate / recalled / expired / fake."""
    code = Code.query.filter_by(token=token).first()
    if not code:
        return jsonify({"state": "fake", "fields": []})

    batch = code.batch
    product = batch.product

    if batch.status == "RECALLED":
        recall = batch.recall
        return jsonify({
            "state": "recalled",
            "fields": [["Batch", batch.batch_no]],
            "note": (f"Recalled {recall.recalled_at.date().isoformat()} — {recall.reason} "
                     "Contact the manufacturer for return instructions.") if recall else None,
        })

    if batch.expiry_date and batch.expiry_date < date.today():
        return jsonify({
            "state": "expired",
            "fields": [["Batch", batch.batch_no], ["Expired", batch.expiry_date.isoformat()]],
        })

    was_activated = code.status == "activated"
    code.scan_count += 1
    db.session.commit()

    if was_activated:
        return jsonify({
            "state": "activated",
            "fields": [
                ["Product", product.name], ["Manufacturer", product.manufacturer.name],
                ["Batch", batch.batch_no],
                ["Mfg / expiry", f"{batch.mfg_date} / {batch.expiry_date}"],
                ["MRP", f"INR {batch.mrp}" if batch.mrp else "—"],
                ["Scan count", str(code.scan_count)],
            ],
        })

    if code.scan_count <= 1:
        return jsonify({
            "state": "firstScan",
            "fields": [["Product", product.name], ["Batch", batch.batch_no],
                       ["Scan count", str(code.scan_count)]],
        })

    return jsonify({
        "state": "duplicate",
        "fields": [["Batch", batch.batch_no], ["Scan count", str(code.scan_count)]],
    })
