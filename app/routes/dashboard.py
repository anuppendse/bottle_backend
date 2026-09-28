from flask import Blueprint, jsonify
from sqlalchemy import func

from app import db
from app.models import Batch, Product, BatchScanCount, normalize_role
from app.decorators import require_permission, current_user

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("")
@require_permission("dashboard")
def get_dashboard():
    user = current_user()

    role = normalize_role(user.role)
    scoped = role == "manufacturer"

    products_q = Product.query
    batches_q = Batch.query

    if scoped:
        products_q = products_q.filter(Product.manufacturer_id == user.manufacturer_id)

        batches_q = batches_q.filter(Batch.manufacturer_id == user.manufacturer_id)

    active_products = products_q.filter(Product.status == "ACTIVE").count()

    total_batches = batches_q.count()

    in_production = batches_q.filter(Batch.status == "IN PRODUCTION").count()

    active = batches_q.filter(Batch.status == "ACTIVE").count()

    recalled = batches_q.filter(Batch.status == "RECALLED").count()

    expired = batches_q.filter(Batch.status == "EXPIRED").count()

    top_active_batches_q = (
        db.session.query(
            Batch.batch_no,
            func.coalesce(func.sum(BatchScanCount.count), 0).label("scan_count"),
        )
        .outerjoin(BatchScanCount, BatchScanCount.batch_no == Batch.batch_no)
        .filter(Batch.status == "ACTIVE")
    )

    if scoped:
        top_active_batches_q = top_active_batches_q.filter(
            Batch.manufacturer_id == user.manufacturer_id
        )

    top_active_batches = (
        top_active_batches_q.group_by(Batch.batch_no)
        .order_by(func.coalesce(func.sum(BatchScanCount.count), 0).desc())
        .limit(5)
        .all()
    )

    top_active_batches_data = [
        {"batchNo": batch_no, "scanCount": scan_count}
        for batch_no, scan_count in top_active_batches
    ]

    top_active_products_q = (
        db.session.query(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            func.coalesce(func.sum(BatchScanCount.count), 0).label("scan_count"),
        )
        .join(Batch, Batch.product_id == Product.id)
        .outerjoin(BatchScanCount, BatchScanCount.batch_no == Batch.batch_no)
        .filter(Product.status == "ACTIVE", Batch.status == "ACTIVE")
    )

    if scoped:
        top_active_products_q = top_active_products_q.filter(
            Product.manufacturer_id == user.manufacturer_id
        )

    top_active_products = (
        top_active_products_q.group_by(Product.id, Product.name)
        .order_by(func.coalesce(func.sum(BatchScanCount.count), 0).desc())
        .limit(5)
        .all()
    )

    top_active_products_data = [
        {"productId": product_id, "productName": product_name, "scanCount": scan_count}
        for product_id, product_name, scan_count in top_active_products
    ]

    return jsonify(
        {
            "scoped": scoped,
            "manufacturerName": (
                user.manufacturer.name if scoped and user.manufacturer else None
            ),
            "stats": {
                "activeProducts": active_products,
                "totalBatches": total_batches,
                "inProduction": in_production,
                "active": active,
                "recalled": recalled,
                "expired": expired,
            },
            "batchStatusBar": [
                {"name": "Active", "v": active},
                {"name": "In Production", "v": in_production},
                {"name": "Expired", "v": expired},
                {"name": "Recalled", "v": recalled},
            ],
            "topActiveBatches": top_active_batches_data,
            "topActiveProducts": top_active_products_data,
        }
    )
