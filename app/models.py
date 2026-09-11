import enum
from sqlalchemy import Enum as SqlEnum
import uuid
from datetime import datetime, date
import hmac
import hashlib
from flask import current_app


from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db
from app.crypto import EncryptedString

UUID_LEN = 36  # length of str(uuid.uuid4())


def gen_uuid() -> str:
    return str(uuid.uuid4())


def _enum_value(v):
    """Unwraps a plain enum.Enum member to its .value for JSON
    serialization — plain enums (unlike StrEnum) aren't JSON-serializable
    on their own. Passes through non-enum values unchanged."""
    return v.value if hasattr(v, "value") else v


def _enum_column_type(enum_cls, name):
    """A db.Enum() type that stores/serializes each member's .value
    string (e.g. "Admin", "IN PRODUCTION") rather than its .name
    (e.g. "ADMIN", "IN_PRODUCTION") — keeps the DB row and JSON output
    identical to what the app used before these were plain strings.
    Build ONE of these per enum class and reuse the same object on
    every column that uses it (see ROLE_ENUM_TYPE below) — Postgres
    creates a real named enum type per distinct object, so reusing it
    avoids trying to (and failing to) create the same type twice."""
    return db.Enum(enum_cls, name=name, values_callable=lambda x: [e.value for e in x])


# ------------------------------------------------------------------
# Roles. Only these three are valid — "Dispatch Agent" and "Label
# Manufacturer" have been removed as roles. Dispatch Console access
# is still reachable — it's just an assignable permission on
# Admin/Manufacturer accounts, same as any other page in the tree below.
# ------------------------------------------------------------------
class Role(enum.Enum):
    ADMIN = "ADMIN"
    MANUFACTURER = "MANUFACTURER"
    EMPLOYEE = "EMPLOYEE"


ROLES = [
    r.value for r in Role
]  # kept as a plain list — existing code iterates/validates against it
ROLE_ENUM_TYPE = _enum_column_type(Role, "role_enum")


class BatchStatus(enum.Enum):
    IN_PRODUCTION = "IN PRODUCTION"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    RECALLED = "RECALLED"


BATCH_STATUSES = [s.value for s in BatchStatus]
BATCH_STATUS_ENUM_TYPE = _enum_column_type(BatchStatus, "batch_status_enum")


class GenerationLevel(enum.Enum):
    BATCH = "BATCH"
    UNIT = "UNIT"


GENERATION_LEVELS = [g.value for g in GenerationLevel]
GENERATION_LEVEL_ENUM_TYPE = _enum_column_type(GenerationLevel, "generation_level_enum")


class RedownloadStatus(enum.Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


REDOWNLOAD_STATUSES = [s.value for s in RedownloadStatus]
REDOWNLOAD_STATUS_ENUM_TYPE = _enum_column_type(
    RedownloadStatus, "redownload_status_enum"
)


class CodeType(enum.Enum):
    QR = "QR"
    BARCODE = "BARCODE"
    BOTH = "BOTH"


class RecordStatus(enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


CODE_TYPES = [c.value for c in CodeType]
CODE_TYPE_ENUM_TYPE = _enum_column_type(CodeType, "code_type_enum")


def normalize_role(role_text: str) -> str:
    """Maps a `role` string (or Role enum member — StrEnum members are
    plain strings, so .strip()/.lower() work the same either way) to
    the internal system role used for data scoping (which manufacturer's
    data a user sees) and for the Admin-only Setup check. This is a
    plain function, not a model property — call it as
    normalize_role(user.role) wherever the old user.system_role was used."""
    t = role_text.value.strip().lower()
    if t == Role.ADMIN.value.lower():
        return t
    if t == Role.MANUFACTURER.value.lower():
        return t
    return Role.EMPLOYEE.value.strip().lower()


# ------------------------------------------------------------------
# Permissions live entirely in the database:
#   Permission          — the tree of assignable pages (key/parent/order)
#   RolePermission       — per-role defaults (role, key, granted)
#   UserPermission        — per-user grants (user, key, granted)
# No `assignable` flag on Permission: "setup" is simply never inserted
# into RolePermission (no role ever defaults to it) and is excluded from
# the assignable tree by key in the /api/permissions route — access to
# it is enforced purely by the Admin-only check in require_permission().
# ------------------------------------------------------------------
class Permission(db.Model):
    """A node in the permissions tree (e.g. 'products' or its child
    'products.add')."""

    __tablename__ = "permissions"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    label = db.Column(db.String(100), nullable=True)
    parent_key = db.Column(
        db.String(50), db.ForeignKey("permissions.key"), nullable=True
    )
    sort_order = db.Column(db.Integer, nullable=True, default=0)
    children = db.relationship(
        "Permission", backref=db.backref("parent", remote_side=[key])
    )



class RolePermission(db.Model):
    """The default permission set for a role — one row per
    (role, permission_key). `granted` mirrors UserPermission's
    true/false flag rather than presence-of-row being the only
    signal."""

    __tablename__ = "role_permissions"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    role = db.Column(ROLE_ENUM_TYPE, nullable=False)
    permission_id = db.Column(
        db.Integer, db.ForeignKey("permissions.id"), nullable=False
    )
    granted = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        db.UniqueConstraint("role", "permission_id", name="uq_role_permission"),
    )


def default_permissions_for_role(role_name: str):
    """The default permission set for a role. Only granted=True rows
    count. Matches role_name case-insensitively in Python first, then
    queries with an exact match — db.func.lower() can't be applied
    directly to a native Postgres enum column, so the case-folding has
    to happen before the query, not inside it."""
    if not role_name:
        return []
    canonical = next(
        (r for r in Role if r.value.lower() == role_name.strip().lower()), None
    )
    if not canonical:
        return []
    rows = RolePermission.query.filter(
        RolePermission.role == canonical,
        RolePermission.granted.is_(True),
    ).all()
    return [r.permission_id for r in rows]


class UserPermission(db.Model):
    """A single user's grant for a single permission. `granted` lets a
    permission be explicitly turned on/off — the row is kept either way,
    only the flag flips — so 'revoked' is distinguishable from 'never
    granted'."""

    __tablename__ = "user_permissions"
    user_id = db.Column(
        db.String(UUID_LEN), db.ForeignKey("users.id"), primary_key=True
    )
    permission_id = db.Column(
        db.Integer, db.ForeignKey("permissions.id"), primary_key=True
    )
    granted = db.Column(db.Boolean, nullable=False, default=True)

    permission = db.relationship("Permission")

    def to_dict(self):
        return {"permission_id": self.permission_id, "granted": self.granted}


def get_user_permissions(user_id: str):
    """Replaces the old User.permissions @property — call this instead
    wherever a user's granted permission keys are needed."""
    rows = UserPermission.query.filter_by(user_id=user_id, granted=True).all()
    return sorted(r.permission_id for r in rows)


class Category(db.Model):
    """Product category — its own table with CRUD (see routes/categories.py)
    instead of a free-typed string on Product."""

    __tablename__ = "categories"
    id = db.Column(db.String(UUID_LEN), primary_key=True, default=gen_uuid)
    name = db.Column(db.String(100), nullable=False, unique=True)

    products = db.relationship("Product", backref="category", lazy=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class Manufacturer(db.Model):
    __tablename__ = "manufacturers"
    id = db.Column(db.String(UUID_LEN), primary_key=True, default=gen_uuid)
    name = db.Column(db.String(200), nullable=False, unique=True)
    code_type = db.Column(
        SqlEnum(CodeType, name="manufacturer_code_type_enum"),
        nullable=False,
        default=CodeType.BOTH,  # was RecordStatus.ACTIVE — wrong enum type
    )
    generation_level = db.Column(
        SqlEnum(GenerationLevel, name="manufacturer_generation_level_enum"),
        nullable=False,
        default=GenerationLevel.UNIT,  # was RecordStatus.ACTIVE — wrong enum type
    )
    status = db.Column(
        SqlEnum(RecordStatus, name="manufacturer_enum"),
        nullable=False,
        default=RecordStatus.ACTIVE,
    )
    company_name = db.Column(db.String(200), nullable=True)
    gstin = db.Column(db.String(40), nullable=True)
    contact_email = db.Column(db.String(200), nullable=True)
    contact_phone = db.Column(db.String(40), nullable=True)

    products = db.relationship("Product", backref="manufacturer", lazy=True)
    users = db.relationship("User", backref="manufacturer", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "codeType": self.code_type.value,
            "generationLevel": self.generation_level.value,  # was self.generation_leve (typo, AttributeError)
            "companyName": self.company_name,
            "gstin": self.gstin,
            "contactEmail": self.contact_email,
            "contactPhone": self.contact_phone,
        }


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.String(UUID_LEN), primary_key=True, default=gen_uuid)
    name = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(50), nullable=False, unique=True)
    email = db.Column(db.String(200), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(SqlEnum(Role, name="user_role_enum"), nullable=False)
    manufacturer_id = db.Column(
        db.String(UUID_LEN), db.ForeignKey("manufacturers.id"), nullable=True
    )
    status = db.Column(
        SqlEnum(RecordStatus, name="user_status_enum"),
        nullable=False,
        default=RecordStatus.ACTIVE,
    )
    grants = db.relationship(
        "UserPermission", backref="user", cascade="all, delete-orphan", lazy="subquery"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def set_permissions(self, keys):
        """Replaces the user's full grant set: keys not in `keys` are
        removed, everything in `keys` ends up with granted=True."""
        keys = {k for k in (keys or []) if k}
        existing = {g.permission_key: g for g in self.grants}

        for key, grant in list(existing.items()):
            if key not in keys:
                db.session.delete(grant)

        valid_keys = (
            {p.key for p in Permission.query.filter(Permission.key.in_(keys)).all()}
            if keys
            else set()
        )
        for key in valid_keys:
            if key in existing:
                existing[key].granted = True
            else:
                db.session.add(
                    UserPermission(user_id=self.id, permission_key=key, granted=True)
                )

    def set_permission(self, key, granted=True):
        """Toggles a single permission on/off without touching the rest
        of the grant set."""
        existing = next((g for g in self.grants if g.permission_key == key), None)
        if existing:
            existing.granted = granted
        elif Permission.query.get(key):
            db.session.add(
                UserPermission(user_id=self.id, permission_key=key, granted=granted)
            )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "username": self.username,
            "email": self.email,
            "role": self.role.value,
            "systemRole": self.role.value,
            "manufacturer": self.manufacturer.name if self.manufacturer else "—",
            "manufacturerId": (
                self.manufacturer_id if self.manufacturer_id is not None else None
            ),
            "status": self.status.value,
            "permissions": get_user_permissions(self.id),
        }


class Product(db.Model):
    """Core catalog data only — no batch-specific fields like a
    manufacturing date (that lives on Batch). Shelf life is owned
    directly by the product, not resolved from a manufacturer default."""

    __tablename__ = "products"
    id = db.Column(db.String(UUID_LEN), primary_key=True, default=gen_uuid)
    name = db.Column(db.String(200), nullable=False)
    category_id = db.Column(
        db.String(UUID_LEN), db.ForeignKey("categories.id"), nullable=False
    )
    manufacturer_id = db.Column(
        db.String(UUID_LEN), db.ForeignKey("manufacturers.id"), nullable=False
    )
    description = db.Column(db.Text)
    shelf_life_months = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    batches = db.relationship("Batch", backref="product", lazy=True)

    def to_dict(self):
        batches = sorted(self.batches, key=lambda b: b.created_at or datetime.min)
        first_batch = batches[0].batch_no if batches else "—"
        last_batch = batches[-1].batch_no if batches else "—"
        return {
            "id": self.id,
            "name": self.name,
            "categoryId": self.category_id,
            "category": self.category.name if self.category else None,
            "manufacturer": self.manufacturer.name,
            "manufacturerId": self.manufacturer_id,
            "desc": self.description,
            "shelfLifeMonths": self.shelf_life_months,
            "firstBatch": first_batch,
            "lastBatch": last_batch,
            "updated": self.updated_at.isoformat() if self.updated_at else None,
        }


class Batch(db.Model):
    __tablename__ = "batches"
    batch_no = db.Column(db.String(UUID_LEN), primary_key=True, default=gen_uuid)
    product_id = db.Column(
        db.String(UUID_LEN), db.ForeignKey("products.id"), nullable=False
    )
    manufacturer_id = db.Column(
        db.String(UUID_LEN), db.ForeignKey("manufacturers.id"), nullable=False
    )
    mfg_date = db.Column(db.Date, nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    qty = db.Column(db.Integer, nullable=False, default=0)
    mrp = db.Column(db.Numeric(10, 2), nullable=True)
    status = db.Column(
        BATCH_STATUS_ENUM_TYPE, nullable=False, default=BatchStatus.IN_PRODUCTION.value
    )
    # "batch" = one code covers the whole batch (exactly one Code row ever
    # exists for it); "unit" = one code per physical unit (up to `qty`
    # Code rows — tens of thousands for a large batch).
    generation_level = db.Column(
        GENERATION_LEVEL_ENUM_TYPE, nullable=False, default=GenerationLevel.UNIT.value
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(
        db.String(UUID_LEN), db.ForeignKey("users.id"), nullable=True
    )

    codes = db.relationship(
        "Code", backref="batch", lazy=True, cascade="all, delete-orphan"
    )
    recall = db.relationship(
        "Recall", backref="batch", uselist=False, cascade="all, delete-orphan"
    )
    anomalies = db.relationship(
        "Anomaly", backref="batch", lazy=True, cascade="all, delete-orphan"
    )

    def is_expiring_soon(self):
        if _enum_value(self.status) != "ACTIVE" or not self.expiry_date:
            return False
        return (self.expiry_date - date.today()).days <= 30

    def display_status(self):
        return "EXPIRING SOON" if self.is_expiring_soon() else _enum_value(self.status)

    def to_dict(self):
        creator = User.query.get(self.created_by) if self.created_by else None
        return {
            "batch": self.batch_no,
            "productId": self.product_id,
            "productName": self.product.name,
            "manufacturer": self.manufacturer_id,
            "manufacturerName": self.product.manufacturer.name,
            "mfg": self.mfg_date.isoformat() if self.mfg_date else "—",
            "expiry": self.expiry_date.isoformat() if self.expiry_date else "—",
            "qty": self.qty,
            "mrp": float(self.mrp) if self.mrp is not None else None,
            "status": (
                self.status.value if hasattr(self.status, "value") else self.status
            ),
            "displayStatus": self.display_status(),
            "generationLevel": (
                self.generation_level.value
                if hasattr(self.generation_level, "value")
                else self.generation_level
            ),
            "created": self.created_at.isoformat() if self.created_at else None,
            "createdBy": creator.name if creator else None,
            "codesGenerated": len(self.codes),
            "codesActivated": sum(1 for c in self.codes if c.status == "activated"),
        }


class Code(db.Model):
    """A single QR/barcode token. If the parent batch's
    generation_level is 'batch', exactly one Code row ever exists for
    that batch_no (the code represents the whole batch). If 'unit',
    one row is minted per physical unit — up to `qty` rows (tens of
    thousands for a large batch).

    `token` is intentionally NOT a UUID: it's the actual business code
    printed/encoded on the physical label, generated by
    Code.generate_token() — random, non-sequential.

    `payload` holds the JSON the label manufacturer needs to render the
    physical QR/barcode: {"code", "batchNumber", "type", "encodedValue"}.
    No images are generated server-side — the label manufacturer's own
    machine renders the QR/barcode from this data."""

    __tablename__ = "codes"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    token = db.Column(db.String(120), nullable=False, unique=True)
    batch_no = db.Column(
        db.String(UUID_LEN), db.ForeignKey("batches.batch_no"), nullable=False
    )
    status = db.Column(
        db.String(20), nullable=False, default="issued"
    )  # issued | activated
    scan_count = db.Column(db.Integer, nullable=False, default=0)
    activated_at = db.Column(db.DateTime, nullable=True)
    activated_by = db.Column(
        db.String(UUID_LEN), db.ForeignKey("users.id"), nullable=True
    )
    code_type = db.Column(db.String(20), nullable=False, default="QR")
    payload = db.Column(db.JSON, nullable=True)

    @staticmethod
    def generate_token() -> str:
        return uuid.uuid4().hex[:10].upper()

    def build_payload(self) -> dict:
        return {
            "code": self.token,
            "batchNumber": self.batch_no,
            "type": self.code_type,
            "url": f"{current_app.config['SCAN_BASE_URL']}/scan/{self.token}",
        }

    @staticmethod
    def verify_payload(payload: dict):
        token = payload.get("code")
        if not token:
            return None
        return Code.query.filter_by(token=token).first()

    def to_dict(self):
        return {
            "token": self.token,
            "batch": self.batch_no,
            "status": self.status,
            "scanCount": self.scan_count,
            "activatedAt": self.activated_at.isoformat() if self.activated_at else None,
            "codeType": self.code_type,
        }


class Recall(db.Model):
    __tablename__ = "recalls"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    batch_no = db.Column(
        db.String(UUID_LEN),
        db.ForeignKey("batches.batch_no"),
        nullable=False,
        unique=True,
    )
    reason = db.Column(db.Text, nullable=False)
    recalled_by = db.Column(
        db.String(UUID_LEN), db.ForeignKey("users.id"), nullable=False
    )
    recalled_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        recaller = User.query.get(self.recalled_by)
        b = self.batch
        return {
            "batch": self.batch_no,
            "productId": b.product_id,
            "productName": b.product.name,
            "manufacturer": b.product.manufacturer.name,
            "reason": self.reason,
            "recalledBy": f"{recaller.name} ({recaller.role})" if recaller else "—",
            "date": self.recalled_at.isoformat() if self.recalled_at else None,
            "status": "RECALLED",
        }


class Anomaly(db.Model):
    __tablename__ = "anomalies"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    batch_no = db.Column(
        db.String(UUID_LEN), db.ForeignKey("batches.batch_no"), nullable=False
    )
    text = db.Column(db.Text, nullable=False)
    severity = db.Column(
        db.String(10), nullable=False, default="medium"
    )  # low | medium | high
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "batch": self.batch_no,
            "productName": self.batch.product.name,
            "text": self.text,
            "severity": self.severity,
        }


class CsvExport(db.Model):
    """One row per generated label batch export — tracks whether the
    first (free) download has already been used, per the rule that a
    redownload after that needs Admin approval."""

    __tablename__ = "csv_exports"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    batch_no = db.Column(
        db.String(UUID_LEN), db.ForeignKey("batches.batch_no"), nullable=False
    )
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    first_download_used = db.Column(db.Boolean, nullable=False, default=False)

    batch = db.relationship(
        "Batch",
        foreign_keys=[batch_no],
        primaryjoin="CsvExport.batch_no == Batch.batch_no",
    )

    def to_dict(self):
        b = self.batch
        return {
            "id": self.id,
            "batch": self.batch_no,
            "productId": b.product_id,
            "manufacturer": b.product.manufacturer.name,
            "manufacturerId": b.manufacturer_id,
            "date": self.generated_at.isoformat() if self.generated_at else None,
            "status": b.status,
            "firstDownloadAvailable": not self.first_download_used,
        }


class RedownloadRequest(db.Model):
    __tablename__ = "redownload_requests"
    id = db.Column(db.String(UUID_LEN), primary_key=True, default=gen_uuid)
    requested_by = db.Column(
        db.String(UUID_LEN), db.ForeignKey("users.id"), nullable=False
    )
    batch_no = db.Column(
        db.String(UUID_LEN), db.ForeignKey("batches.batch_no"), nullable=False
    )
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(
        REDOWNLOAD_STATUS_ENUM_TYPE,
        nullable=False,
        default=RedownloadStatus.PENDING.value,
    )
    review_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        requester = User.query.get(self.requested_by)
        return {
            "id": self.id,
            "requestedBy": requester.name if requester else "—",
            "role": requester.role if requester else "—",
            "batch": self.batch_no,
            "reason": self.reason,
            "date": self.created_at.isoformat() if self.created_at else None,
            "status": self.status,
        }


class SystemSetup(db.Model):
    """Per-manufacturer system defaults + company profile (keyed by
    manufacturer_id — one row per manufacturer, not a global singleton).
    default_code_type and default_generation_level are encrypted at
    rest via EncryptedString."""

    __tablename__ = "system_setup"
    manufacturer_id = db.Column(
        db.String(UUID_LEN), db.ForeignKey("manufacturers.id"), primary_key=True
    )
    default_code_type = db.Column(
        EncryptedString(255), nullable=False, default="Both"
    )  # QR Code | Barcode | Both
    default_generation_level = db.Column(
        EncryptedString(255), nullable=False, default="Unit-level"
    )
    company_name = db.Column(db.String(200))
    gstin = db.Column(db.String(40))
    contact_email = db.Column(db.String(200))
    contact_phone = db.Column(db.String(40))

    manufacturer = db.relationship(
        "Manufacturer", backref=db.backref("setup", uselist=False)
    )

    def to_dict(self):
        return {
            "manufacturerId": self.manufacturer_id,
            "manufacturerName": self.manufacturer.name if self.manufacturer else None,
            "defaultCodeType": self.default_code_type,
            "defaultGenerationLevel": self.default_generation_level,
            "companyName": self.company_name,
            "gstin": self.gstin,
            "contactEmail": self.contact_email,
            "contactPhone": self.contact_phone,
        }
