from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import Batch, normalize_role, BatchStatus
from app.decorators import require_permission, current_user

dispatch_bp = Blueprint("dispatch", __name__)


def _scope_query(q, user):
    """
    Manufacturers can only see batches belonging to
    their manufacturer.

    Admins can see all batches.
    """
    if normalize_role(user.role) == "manufacturer":
        return q.filter_by(manufacturer_id=user.manufacturer_id)

    return q


@dispatch_bp.get("/batches")
@require_permission("dispatchConsole")
def dispatch_ready_batches():
    """
    Return only batches that are READY TO DISPATCH.

    These batches are displayed in the Dispatch Console
    dropdown.
    """

    user = current_user()

    rows = (
        _scope_query(Batch.query, user)
        .filter(Batch.status == BatchStatus.IN_PRODUCTION)
        .order_by(Batch.created_at.desc())
        .all()
    )

    return jsonify(
        [
            {
                "batch": b.batch_no,
                "productName": b.product.name if b.product else None,
                "qty": b.qty,
                "status": b.status,
            }
            for b in rows
        ]
    )


@dispatch_bp.post("/activate")
@require_permission("dispatchConsole")
def activate_batch():
    """
    Activate a batch from the Dispatch Console.

    Only READY TO DISPATCH batches can be activated.

    READY TO DISPATCH -> ACTIVE
    """

    user = current_user()

    data = request.get_json(silent=True) or {}

    batch_no = (data.get("batch") or "").strip()

    if not batch_no:
        return jsonify({"error": "Batch number is required."}), 400

    # Apply manufacturer scoping first
    batch = _scope_query(Batch.query, user).filter(Batch.batch_no == batch_no).first()

    if not batch:
        return jsonify({"error": "Batch not found."}), 404

    # Critical validation:
    # The batch MUST be READY TO DISPATCH.
    if batch.status != BatchStatus.IN_PRODUCTION:
        return (
            jsonify(
                {
                    "error": (
                        "Only batches with READY TO DISPATCH status "
                        "can be activated."
                    )
                }
            ),
            400,
        )

    # Activate the batch
    batch.status = "ACTIVE"

    db.session.commit()

    return jsonify(
        {
            "message": "Batch activated successfully.",
            "batch": batch.batch_no,
            "product": batch.product.name if batch.product else None,
            "status": batch.status,
            "activatedBy": user.name,
        }
    )


@dispatch_bp.get("/history")
@require_permission("dispatchConsole")
def dispatch_history():
    """
    Return batches activated by the current user.

    We no longer depend on activated Code rows because
    Dispatch Console now activates the batch itself.
    """

    user = current_user()

    query = (
        Batch.query.filter(Batch.status == BatchStatus.ACTIVE)
        .order_by(Batch.created_at.desc())
    
    )

    rows = query.all()

    return jsonify(
        [
            {
                "batch": b.batch_no,
                "product": b.product.name if b.product else None,
                "status": b.status,
                "when": b.created_at.isoformat() if b.created_at else None,
            }
            for b in rows
        ]
    )
