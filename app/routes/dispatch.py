from datetime import datetime

from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import Batch, Code, normalize_role
from app.decorators import require_permission, current_user

dispatch_bp = Blueprint("dispatch", __name__)


def _scope_query(q, user):
    if normalize_role(user.role) == "manufacturer":
        return q.filter_by(manufacturer_id=user.manufacturer_id)
    return q


@dispatch_bp.get("/batches")
@require_permission("dispatchConsole")
def dispatch_active_batches():
    user = current_user()
    rows = _scope_query(Batch.query, user).filter_by(status="ACTIVE").all()
    return jsonify([{
        "batch": b.batch_no,
        "productName": b.product.name,
        "qty": b.qty,
        "activated": sum(1 for c in b.codes if c.status == "activated"),
        "total": len(b.codes) or b.qty,
    } for b in rows])


@dispatch_bp.post("/activate")
@require_permission("dispatchConsole")
def activate_code():
    """Locks genuine status onto a token at the point of physical
    dispatch. If the scanned token isn't a pre-minted one, a fresh
    token is minted on the fly — same fallback as the frontend mock."""
    user = current_user()
    data = request.get_json(silent=True) or {}
    batch_no = data.get("batch")
    token_in = (data.get("token") or "").strip()

    batch = _scope_query(Batch.query, user).filter_by(batch_no=batch_no).first()
    if not batch:
        return jsonify({"error": "Batch not found."}), 404
    if batch.status != "ACTIVE":
        return jsonify({"error": "Only active batches can be dispatched."}), 400

    if batch.generation_level == "batch":
        # Exactly one Code row represents the whole batch — activate that
        # single row rather than minting/matching per scan.
        code = batch.codes[0] if batch.codes else None
        if not code:
            code = Code(token=Code.generate_token(batch_no, 1), batch_no=batch_no, scan_count=0)
            db.session.add(code)
    else:
        code = Code.query.filter_by(batch_no=batch_no, token=token_in).first() if token_in else None
        if not code:
            seq = len(batch.codes) + 1
            token = token_in or Code.generate_token(batch_no, seq)
            code = Code.query.filter_by(token=token).first()
            if not code:
                code = Code(token=token, batch_no=batch_no, scan_count=0)
                db.session.add(code)

    code.status = "activated"
    code.activated_at = datetime.utcnow()
    code.activated_by = user.id
    code.scan_count = max(code.scan_count or 0, 1)
    db.session.commit()

    return jsonify({
        "token": code.token,
        "batch": batch_no,
        "product": batch.product.name,
        "activatedAt": code.activated_at.isoformat(),
        "activatedBy": user.name,
    })


@dispatch_bp.get("/history")
@require_permission("dispatchConsole")
def dispatch_history():
    user = current_user()
    q = Code.query.filter(Code.status == "activated").filter(Code.activated_by == user.id)
    rows = q.order_by(Code.activated_at.desc()).limit(100).all()
    return jsonify([{
        "token": c.token,
        "batch": c.batch_no,
        "product": c.batch.product.name,
        "when": c.activated_at.isoformat() if c.activated_at else None,
        "by": user.name,
    } for c in rows])
