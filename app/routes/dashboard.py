from flask import Blueprint, jsonify

from app.models import Batch, Product, Anomaly, normalize_role
from app.decorators import require_permission, current_user

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("")
@require_permission("dashboard")
def get_dashboard():
    user = current_user()
    scoped = normalize_role(user.role) == "manufacturer"
    mfr_id = user.manufacturer_id if scoped else None

    products_q = Product.query
    batches_q = Batch.query
    if scoped:
        products_q = products_q.filter_by(manufacturer_id=mfr_id)
        batches_q = batches_q.filter_by(manufacturer_id=mfr_id)

    batches = batches_q.all()
    status_counts = {"IN PRODUCTION": 0, "ACTIVE": 0, "EXPIRED": 0, "RECALLED": 0}
    for b in batches:
        status_counts[b.status] = status_counts.get(b.status, 0) + 1

    anomalies_q = Anomaly.query
    if scoped:
        anomalies_q = anomalies_q.join(Batch).filter(Batch.manufacturer_id == mfr_id)
    active_batch_nos = {b.batch_no for b in batches if b.status == "ACTIVE"}
    anomalies = [a for a in anomalies_q.all() if a.batch_no in active_batch_nos]

    top_batches = list(dict.fromkeys(a.batch_no for a in anomalies))[:5]
    top_products = list(dict.fromkeys(a.batch.product.name for a in anomalies))[:5]

    return jsonify({
        "scoped": scoped,
        "manufacturerName": user.manufacturer.name if scoped and user.manufacturer else None,
        "stats": {
            "totalProducts": products_q.count(),
            "totalBatches": len(batches),
            "inProduction": status_counts["IN PRODUCTION"],
            "active": status_counts["ACTIVE"],
            "recalled": status_counts["RECALLED"],
            "expired": status_counts["EXPIRED"],
        },
        "batchStatusBar": [
            {"name": "Active", "v": status_counts["ACTIVE"]},
            {"name": "In Production", "v": status_counts["IN PRODUCTION"]},
            {"name": "Expired", "v": status_counts["EXPIRED"]},
            {"name": "Recalled", "v": status_counts["RECALLED"]},
        ],
        "topActiveBatches": top_batches,
        "topActiveProducts": top_products,
    })
