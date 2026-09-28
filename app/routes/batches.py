from datetime import datetime

from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import Batch, BatchStatus, Product, Recall, Anomaly, normalize_role, get_user_permissions
from app.decorators import require_permission, current_user

from sqlalchemy import or_

batches_bp = Blueprint("batches", __name__)

_SORT_ORDER = {
    "IN PRODUCTION": 0,
    "ACTIVE": 1,
    "RECALLED": 2,
    "EXPIRED": 3,
}


def _scope_query(q, user):
    if normalize_role(user.role) == "manufacturer":
        return q.filter_by(manufacturer_id=user.manufacturer_id)
    return q

def generate_batch_id(manufacturer_seq_no: int, sequence: int, gen_date: date = None) -> str:
    gen_date = gen_date or date.today()
    rev_year = str(gen_date.year)[::-1]
    rev_month = f"{gen_date.month:02d}"[::-1]
    rev_day = f"{gen_date.day:02d}"[::-1]
    reversed_date = f"{rev_year}{rev_month}{rev_day}"
    return f"BTH-{manufacturer_seq_no:04d}-{reversed_date}-{sequence:03d}"

@batches_bp.get("")
@require_permission("batches")
def list_batches():
    user = current_user()
    # rows = _scope_query(Batch.query, user).all()
    # rows.sort(key=lambda b: (_SORT_ORDER.get(b.status, 9), b.batch_no))
    # return jsonify([b.to_dict() for b in rows])
    q = _scope_query(Batch.query, user)

    status = request.args.get("status", "").strip()

    # Status filter
    if status and status != "ALL":
        q = q.filter(Batch.status == status)

    search = request.args.get("search", "").strip()
    
    if search:
        q = q.join(Product, Batch.product_id == Product.id).filter(
        or_(
            Batch.batch_no.ilike(f"%{search}%"),
            Product.name.ilike(f"%{search}%")
        )
    )

    rows = q.all()

    rows.sort(
    key=lambda b: (
        _SORT_ORDER.get(
            b.status.value if hasattr(b.status, "value") else str(b.status),
            9
        ),
        b.batch_no
    )
)

    return jsonify([b.to_dict() for b in rows])

@batches_bp.get("/<batch_or_product_id>")
@require_permission("batches")
def get_batch_or_product_detail(batch_or_product_id):
    """Mirrors the frontend's DetailPage: id may be a batch number OR a
    bare product id (in which case the most recent batch is shown)."""
    user = current_user()
    batch = _scope_query(Batch.query, user).filter_by(batch_no=batch_or_product_id).first()
    if not batch:
        batch = (_scope_query(Batch.query, user)
                 .filter_by(product_id=batch_or_product_id)
                 .order_by(Batch.created_at.desc()).first())
    if not batch:
        product = Product.query.get(batch_or_product_id)
        if not product or (normalize_role(user.role) == "manufacturer" and product.manufacturer_id != user.manufacturer_id):
            return jsonify({"error": "This product or batch could not be located."}), 404
        return jsonify({"product": product.to_dict(), "batch": None, "recall": None, "anomaly": None})

    can_see_alerts = normalize_role(user.role) in ("admin", "manufacturer")
    anomaly = Anomaly.query.filter_by(batch_no=batch.batch_no).first() if can_see_alerts else None
    return jsonify({
        "product": batch.product.to_dict(),
        "batch": batch.to_dict(),
        "recall": batch.recall.to_dict() if batch.recall else None,
        "anomaly": anomaly.to_dict() if anomaly else None,
    })


@batches_bp.post("/<batch_no>/recall")
@require_permission("batches")
def recall_batch(batch_no):
    user = current_user()
    batch = _scope_query(Batch.query, user).filter_by(batch_no=batch_no).first()
    if not batch:
        return jsonify({"error": "Batch not found."}), 404
    if "batches.recall" not in get_user_permissions(user.id) and normalize_role(user.role) != "admin":
        return jsonify({"error": "403 — you don't have permission to recall batches."}), 403
    if batch.status != BatchStatus.ACTIVE:
        return jsonify({"error": "Only active batches can be recalled."}), 400

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"error": "Reason for recall is required."}), 400
    
    batch.status = BatchStatus.RECALLED 
    recall = Recall(batch_no=batch.batch_no, reason=reason, recalled_by=user.id,
                     recalled_at=datetime.utcnow())
    db.session.add(recall)
    db.session.commit()
    return jsonify(recall.to_dict())
