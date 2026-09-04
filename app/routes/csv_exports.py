from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import CsvExport, RedownloadRequest, Batch, normalize_role
from app.decorators import require_permission, current_user

csv_bp = Blueprint("csv_exports", __name__)


def _scope_query(q, user):
    if normalize_role(user.role) == "manufacturer":
        return q.join(Batch, CsvExport.batch_no == Batch.batch_no).filter(Batch.manufacturer_id == user.manufacturer_id)
    return q


@csv_bp.get("/exports")
@require_permission("csvDownloads")
def list_exports():
    user = current_user()
    rows = _scope_query(CsvExport.query, user).order_by(CsvExport.generated_at.desc()).all()
    can_direct_download = normalize_role(user.role) in ("admin", "manufacturer")
    out = []
    for r in rows:
        d = r.to_dict()
        d["canDownloadNow"] = can_direct_download or d["firstDownloadAvailable"]
        out.append(d)
    return jsonify(out)


@csv_bp.post("/exports/<int:export_id>/download")
@require_permission("csvDownloads")
def download_export(export_id):
    """Marks the (one-time, non-Admin/Manufacturer) free download as
    used and hands back the batch id to fetch the actual CSV from
    /api/labels/<batch>/csv."""
    user = current_user()
    export = CsvExport.query.get(export_id)
    if not export:
        return jsonify({"error": "Export not found."}), 404
    can_direct_download = normalize_role(user.role) in ("admin", "manufacturer")
    if not can_direct_download and export.first_download_used:
        return jsonify({"error": "This export has already been downloaded once. Request a redownload."}), 403
    if not can_direct_download:
        export.first_download_used = True
        db.session.commit()
    return jsonify({"batch": export.batch_no})


@csv_bp.post("/exports/<int:export_id>/request-redownload")
@require_permission("csvDownloads")
def request_redownload(export_id):
    user = current_user()
    export = CsvExport.query.get(export_id)
    if not export:
        return jsonify({"error": "Export not found."}), 404
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"error": "Reason for request is required."}), 400

    req = RedownloadRequest(requested_by=user.id, batch_no=export.batch_no, reason=reason)
    db.session.add(req)
    db.session.commit()
    return jsonify(req.to_dict()), 201


@csv_bp.get("/requests")
@require_permission("csvRequests")
def list_requests():
    rows = RedownloadRequest.query.order_by(RedownloadRequest.created_at.desc()).all()
    return jsonify([r.to_dict() for r in rows])


@csv_bp.post("/requests/<request_id>/decide")
@require_permission("csvRequests")
def decide_request(request_id):
    req = RedownloadRequest.query.get(request_id)
    if not req:
        return jsonify({"error": "Request not found."}), 404
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("Approved", "Rejected"):
        return jsonify({"error": "status must be Approved or Rejected."}), 400

    req.status = status
    req.review_note = data.get("note")
    if status == "Approved":
        export = CsvExport.query.filter_by(batch_no=req.batch_no).order_by(CsvExport.generated_at.desc()).first()
        if export:
            export.first_download_used = False
    db.session.commit()
    return jsonify(req.to_dict())
