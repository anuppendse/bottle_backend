from datetime import date, datetime

from flask import Blueprint, jsonify

from app.extensions import db
from app.models import Code ,BatchScanCount

scan_bp = Blueprint("scan", __name__)


@scan_bp.get("/<token>")
def scan_code(token):
    code = Code.query.filter_by(token=token).first()
    if not code:
        return jsonify({"result": "fake"}), 404

    batch = code.batch
    product = batch.product

    base = {
        "product": product.name,
        "manufacturer": product.manufacturer.name,
        "batch": batch.batch_no,
        "mfg": batch.mfg_date.isoformat() if batch.mfg_date else None,
        "expiry": batch.expiry_date.isoformat() if batch.expiry_date else None,
        "mrp": float(batch.mrp) if batch.mrp is not None else None,
    }

    batch_status = batch.status.value if hasattr(batch.status, "value") else batch.status

    if batch_status == "RECALLED":
        return jsonify({**base, "result": "recalled"})

    is_expired = batch_status == "EXPIRED" or (
        batch.expiry_date and batch.expiry_date < date.today()
    )
    if is_expired:
        return jsonify({**base, "result": "expired"})

    # Genuine — figure out which of the three "genuine" sub-states applies
    was_already_scanned = code.scan_count > 0
    was_pre_activated = code.activated_by is not None and code.scan_count == 0

    code.scan_count += 1
    if code.scan_count == 1:
        code.activated_at = datetime.utcnow()
        code.status = "activated"

    _increment_batch_scan_count(batch.batch_no, product.id)

    db.session.commit()

    if was_already_scanned:
        result = "already_verified"
    elif was_pre_activated:
        result = "genuine_activated"
    else:
        result = "genuine_first_scan"

    return jsonify({**base, "result": result})

def _increment_batch_scan_count(batch_no, product_id):
    """Get-or-create the scan-count row for this batch and bump it by 1.
    Row-locks an existing row to avoid losing an increment when two
    scans of the same batch land at nearly the same time."""
    row = (
        BatchScanCount.query
        .filter_by(batch_no=batch_no)
        .with_for_update()
        .first()
    )
    if row is None:
        row = BatchScanCount(batch_no=batch_no, product_id=product_id, count=1)
        db.session.add(row)
    else:
        row.count += 1