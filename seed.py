"""
Seeds the database with demo data for the current schema: DB-backed
permission tree / per-manufacturer role defaults, per-manufacturer Setup
rows, a Category table, UUID primary keys throughout, and batch- vs
unit-level code generation. Run with: python seed.py
"""
from datetime import date, datetime

from app import create_app
from app.extensions import db
from app.models import (
    Manufacturer, User, Category, Product, Batch, Code, Recall, Anomaly,
    CsvExport, RedownloadRequest, SystemSetup,
    Permission, RolePermission, default_permissions_for_role,
)

app = create_app()

# ------------------------------------------------------------------
# Permission tree — the source of truth lives in the DB; this is just
# the seed data for it. (key, label, parent_key, section, sort_order)
# ------------------------------------------------------------------
PERMISSION_ROWS = [
    ("dashboard", "Dashboard", None, "Overview", 0),
    ("products", "Products", None, "Operate", 1),
    ("products.add", "Add product", "products", None, 2),
    ("products.edit", "Edit product", "products", None, 3),
    ("labelGeneration", "Label Generation", None, "Operate", 4),
    ("dispatchConsole", "Dispatch Console", None, "Operate", 5),
    ("batches", "Batch Management", None, "Operate", 6),
    ("batches.view", "View only", "batches", None, 7),
    ("batches.recall", "Recall", "batches", None, 8),
    ("recalls", "Recall Management", None, "Operate", 9),
    ("csvDownloads", "CSV Downloads", None, "Operate", 10),
    ("csvRequests", "Redownload Requests", None, "Operate", 11),
    ("users", "Users", None, "Admin only", 12),
    ("setup", "Setup", None, "Admin only", 13),  # never in RolePermission — Admin-only, enforced in code
]

# The default permissions granted to a newly created user of a given
# role, applied whenever they aren't given an explicit permissions list.
GLOBAL_ROLE_DEFAULTS = {
    "Admin": ["dashboard", "products", "products.add", "products.edit", "labelGeneration",
              "dispatchConsole", "batches", "batches.view", "batches.recall", "recalls",
              "csvDownloads", "csvRequests", "users"],
    "Manufacturer": ["dashboard", "products", "products.add", "products.edit", "labelGeneration",
                      "dispatchConsole", "batches", "batches.view", "batches.recall", "recalls",
                      "csvDownloads", "users"],
    "Employee": ["products", "csvDownloads"],
}

with app.app_context():
    db.drop_all()
    db.create_all()

    # ---------------- Manufacturers (UUID ids) ----------------
    kaveri = Manufacturer(name="Kaveri Lubricants Pvt Ltd")
    anveshan = Manufacturer(name="Anveshan Industrial Fluids")
    bharat = Manufacturer(name="Bharat PetroChem Co.")
    db.session.add_all([kaveri, anveshan, bharat])
    db.session.flush()

    # ---------------- Categories ----------------
    cat_engine_oil = Category(name="Engine Oil")
    cat_hydraulic = Category(name="Hydraulic Fluid")
    cat_gear_oil = Category(name="Gear Oil")
    cat_coolant = Category(name="Coolant")
    db.session.add_all([cat_engine_oil, cat_hydraulic, cat_gear_oil, cat_coolant])
    db.session.flush()

    # ---------------- Permissions ----------------
    for key, label, parent_key, section, sort_order in PERMISSION_ROWS:
        db.session.add(Permission(key=key, label=label, parent_key=parent_key,
                                   section=section, sort_order=sort_order))
    db.session.flush()

    # ---------------- Role defaults ----------------
    for role, keys in GLOBAL_ROLE_DEFAULTS.items():
        for key in keys:
            db.session.add(RolePermission(role=role, permission_key=key, granted=True))
    db.session.flush()

    # ---------------- Users (UUID ids) ----------------
    # Only Admin / Manufacturer / Employee are valid roles.
    users_data = [
        dict(name="Rhea Deshmukh", email="rhea.deshmukh@labeltrack.com", role="Admin", manufacturer_id=None, status="Active"),
        dict(name="Arjun Patwardhan", email="arjun.p@kaverilube.com", role="Manufacturer", manufacturer_id=kaveri.id, status="Active"),
        dict(name="Sneha Kulkarni", email="sneha.k@labelworks.in", role="Employee", manufacturer_id=anveshan.id, status="Active"),
        dict(name="Manoj Iyer", email="manoj.iyer@kaverilube.com", role="Employee", manufacturer_id=kaveri.id, status="Inactive"),
        dict(name="Farah Sheikh", email="farah.sheikh@anveshan.in", role="Manufacturer", manufacturer_id=anveshan.id, status="Active"),
        dict(name="Vikram Rao", email="vikram.rao@kaverilube.com", role="Employee", manufacturer_id=kaveri.id, status="Active"),
    ]
    users_by_email = {}
    for u in users_data:
        user = User(name=u["name"], email=u["email"], role=u["role"],
                    manufacturer_id=u["manufacturer_id"], status=u["status"])
        user.set_password("Demo@123")
        db.session.add(user)
        db.session.flush()
        user.set_permissions(default_permissions_for_role(u["role"]))
        users_by_email[u["email"]] = user
    db.session.flush()

    admin_user = users_by_email["rhea.deshmukh@labeltrack.com"]
    mfr_user = users_by_email["arjun.p@kaverilube.com"]
    dispatch_user = users_by_email["vikram.rao@kaverilube.com"]

    # ---------------- Products (UUID ids; category FK; own shelf_life_months) ----------------
    p1042 = Product(name="SynthoShield 20W-40 Engine Oil", category_id=cat_engine_oil.id, manufacturer_id=kaveri.id,
                     description="Fully synthetic 4-stroke engine oil for commercial fleets.", shelf_life_months=24)
    p1043 = Product(name="SynthoShield 15W-50 Engine Oil", category_id=cat_engine_oil.id, manufacturer_id=kaveri.id,
                     description="High-performance synthetic blend for two-wheelers.", shelf_life_months=36)
    p1108 = Product(name="HydroMax Hydraulic Fluid ISO 68", category_id=cat_hydraulic.id, manufacturer_id=anveshan.id,
                     description="Anti-wear hydraulic fluid for industrial machinery.", shelf_life_months=24)
    p1122 = Product(name="TransGuard Gear Oil 90", category_id=cat_gear_oil.id, manufacturer_id=kaveri.id,
                     description="EP gear oil for heavy commercial axles.", shelf_life_months=18)
    p1201 = Product(name="CoolFlow Radiator Coolant", category_id=cat_coolant.id, manufacturer_id=bharat.id,
                     description="Long-life ethylene-glycol based coolant concentrate.", shelf_life_months=48)
    db.session.add_all([p1042, p1043, p1108, p1122, p1201])
    db.session.flush()

    # ---------------- Batches (UUID batch_no; explicit generation_level) ----------------
    batches_data = [
        # Unit-level: one Code row per unit (capped below for seed size).
        dict(product=p1042, mfg=date(2026, 9, 1), expiry=date(2028, 9, 1),
             qty=12000, status="ACTIVE", created=date(2026, 9, 1), mrp=4250, level="unit"),
        dict(product=p1043, mfg=date(2026, 8, 22), expiry=date(2029, 8, 22),
             qty=8500, status="ACTIVE", created=date(2026, 8, 22), mrp=3990, level="unit"),
        dict(product=p1108, mfg=date(2026, 8, 10), expiry=date(2028, 8, 10),
             qty=4200, status="RECALLED", created=date(2026, 8, 10), mrp=5200, level="unit"),
        dict(product=p1122, mfg=date(2025, 2, 2), expiry=date(2026, 8, 2),
             qty=6000, status="EXPIRED", created=date(2025, 2, 2), mrp=2100, level="unit"),
        # Batch-level: exactly ONE Code row represents this whole batch.
        dict(product=p1201, mfg=date(2026, 7, 18), expiry=date(2030, 7, 18),
             qty=15000, status="ACTIVE", created=date(2026, 7, 18), mrp=650, level="batch"),
        dict(product=p1042, mfg=date(2026, 7, 5), expiry=date(2026, 10, 5),
             qty=3000, status="ACTIVE", created=date(2026, 7, 5), mrp=4250, level="unit"),
        dict(product=p1043, mfg=None, expiry=None,
             qty=5000, status="IN PRODUCTION", created=date(2026, 9, 2), mrp=None, level="unit"),
    ]
    batches = []
    for b in batches_data:
        batch = Batch(product_id=b["product"].id, manufacturer_id=b["product"].manufacturer_id,
                       mfg_date=b["mfg"], expiry_date=b["expiry"], qty=b["qty"], mrp=b["mrp"],
                       status=b["status"], generation_level=b["level"],
                       created_at=datetime.combine(b["created"], datetime.min.time()),
                       created_by=mfr_user.id)
        db.session.add(batch)
        batches.append(batch)
    db.session.flush()

    b_engine1, b_engine2, b_hydraulic, b_gear, b_coolant, b_engine3, b_inprod = batches

    # ---------------- Codes ----------------
    # Batch-level batch: exactly one Code row, full stop.
    coolant_code = Code(token="LT-0655-BATCH", batch_no=b_coolant.batch_no)
    db.session.add(coolant_code)

    # Unit-level batches: mint a handful of demo codes each (a real batch
    # of 12,000 would mint 12,000 rows here — capped for seed size).
    demo_activated = {b_engine1.batch_no: "LT-0817-ACT"}
    for batch in [b_engine1, b_engine2, b_hydraulic, b_gear, b_engine3]:
        n = min(batch.qty, 25)
        for i in range(1, n + 1):
            forced = demo_activated.get(batch.batch_no) if i == 1 else None
            token = forced or Code.generate_token(batch.batch_no, i)
            code = Code(token=token, batch_no=batch.batch_no)
            if forced:
                code.status = "activated"
                code.activated_at = datetime.utcnow()
                code.activated_by = dispatch_user.id
            db.session.add(code)

    # A couple of extra fixed demo tokens for the public verify walkthrough
    db.session.add(Code(token="LT-0790-DUP", batch_no=b_engine2.batch_no, scan_count=4))
    db.session.add(Code(token="LT-0754-RCL", batch_no=b_hydraulic.batch_no))
    db.session.flush()

    # ---------------- Recall ----------------
    db.session.add(Recall(batch_no=b_hydraulic.batch_no,
                           reason="Viscosity out of spec detected in QA retest of retained sample.",
                           recalled_by=admin_user.id, recalled_at=datetime(2026, 8, 29, 11, 20)))

    # ---------------- Anomalies ----------------
    anomalies = [
        (b_engine2, "Same token scanned in Pune and Chennai within 40 minutes — possible clone.", "high"),
        (b_coolant, "Batch-level code scanned 14 times in one week — well above expected rate.", "medium"),
        (b_engine1, "Batch is scanning at roughly 3x the rate of comparable batches this month.", "medium"),
        (b_engine3, "Same token scanned twice nine minutes apart from IP addresses in different states.", "high"),
        (b_hydraulic, "Scans continued for 48 hours after this batch was recalled.", "high"),
    ]
    for batch, text, severity in anomalies:
        db.session.add(Anomaly(batch_no=batch.batch_no, text=text, severity=severity))

    # ---------------- CSV exports + redownload requests ----------------
    exports = [
        CsvExport(batch_no=b_engine1.batch_no, generated_at=datetime(2026, 9, 1), first_download_used=True),
        CsvExport(batch_no=b_engine2.batch_no, generated_at=datetime(2026, 8, 22), first_download_used=False),
        CsvExport(batch_no=b_hydraulic.batch_no, generated_at=datetime(2026, 8, 10), first_download_used=False),
        CsvExport(batch_no=b_gear.batch_no, generated_at=datetime(2025, 2, 2), first_download_used=False),
    ]
    db.session.add_all(exports)
    db.session.flush()

    sneha = users_by_email["sneha.k@labelworks.in"]
    manoj = users_by_email["manoj.iyer@kaverilube.com"]
    farah = users_by_email["farah.sheikh@anveshan.in"]
    db.session.add_all([
        RedownloadRequest(requested_by=sneha.id, batch_no=b_engine2.batch_no,
                           reason="Original export corrupted during transfer to print vendor.",
                           status="Pending", created_at=datetime(2026, 8, 31)),
        RedownloadRequest(requested_by=manoj.id, batch_no=b_gear.batch_no,
                           reason="Needed for a closed batch's compliance audit.",
                           status="Approved", created_at=datetime(2026, 8, 27)),
        RedownloadRequest(requested_by=farah.id, batch_no=b_hydraulic.batch_no,
                           reason="Re-verifying recalled batch codes against distributor returns.",
                           status="Rejected", created_at=datetime(2026, 8, 25)),
    ])

    # ---------------- Per-manufacturer Setup rows (encrypted fields) ----------------
    db.session.add(SystemSetup(
        manufacturer_id=kaveri.id, default_code_type="Both", default_generation_level="Unit-level",
        company_name="Kaveri Lubricants Pvt Ltd", gstin="27AACCK1234F1Z5",
        contact_email="ops@kaverilube.com", contact_phone="+91 20 4567 8900",
    ))
    db.session.add(SystemSetup(
        manufacturer_id=anveshan.id, default_code_type="QR Code", default_generation_level="Batch-level",
        company_name="Anveshan Industrial Fluids", gstin="24AACCA5678G1Z2",
        contact_email="ops@anveshan.in", contact_phone="+91 265 234 5678",
    ))
    db.session.add(SystemSetup(
        manufacturer_id=bharat.id, default_code_type="Barcode", default_generation_level="Unit-level",
        company_name="Bharat PetroChem Co.", gstin="37AACCB9012H1Z8",
        contact_email="ops@bharatpetrochem.in", contact_phone="+91 891 345 6789",
    ))

    db.session.commit()
    print("Seed complete.")
    print(f"Batch-level demo batch (1 Code row total): {b_coolant.batch_no}  token=LT-0655-BATCH")
    print(f"Unit-level demo batch (many Code rows):     {b_engine1.batch_no}  token=LT-0817-ACT (activated)")
    print("Demo logins (all use password Demo@123):")
    for u in users_data:
        print(f"  {u['role']:<14} {u['email']}")
