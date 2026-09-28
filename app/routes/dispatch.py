from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import Batch, BatchActivation, normalize_role, BatchStatus
from app.decorators import require_permission, current_user
from datetime import datetime

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
                # "status": b.status,
                "status": b.status.value if hasattr(b.status, "value") else b.status,
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
    batch.status = BatchStatus.ACTIVE

    activated_at = datetime.utcnow()
    
    activation = BatchActivation(
    batch_no=batch.batch_no,
    activated_at=activated_at,
    activated_by=user.id
    )

    db.session.add(activation)

    db.session.commit()

    return jsonify(
        {
            "message": "Batch activated successfully.",
            "batch": batch.batch_no,
            "product": batch.product.name if batch.product else None,
            "status": batch.status.value,
            "activatedBy": user.name,
            "activatedAt": activated_at.isoformat(),
        }
    )


@dispatch_bp.get("/history")
@require_permission("dispatchConsole")
def dispatch_history():
    user = current_user()

    query = (
        BatchActivation.query
        .join(Batch, Batch.batch_no == BatchActivation.batch_no)
        .order_by(BatchActivation.activated_at.desc())
    )

    if normalize_role(user.role) == "manufacturer":
        query = query.filter(Batch.manufacturer_id == user.manufacturer_id)

    rows = query.all()

    return jsonify(
        [
            {
                "id": activation.id,
                "batch": activation.batch_no,
                "activatedBy": (
                    activation.activated_by_user.name
                    if getattr(activation, "activated_by_user", None)
                    else None
                ),
                "when": (
                    activation.activated_at.isoformat()
                    if activation.activated_at
                    else None
                ),
            }
            for activation in rows
        ]
    )