from app.extensions import db
from app.models import Code


def _unique_token(max_attempts: int = 5) -> str:
    """Random tokens can theoretically collide (very unlikely at 10
    hex chars, but cheap to guard against) — retry a few times before
    giving up."""
    for _ in range(max_attempts):
        token = Code.generate_token()
        if not Code.query.filter_by(token=token).first():
            return token
    raise RuntimeError("Could not generate a unique token — try again.")


def mint_code(batch, code_type: str) -> list:
    """Creates one or two Code rows for `batch`, depending on code_type:
      - "QR" or "Barcode": one row, that type.
      - "Both": TWO rows — one type="QR", one type="Barcode" — sharing
        the same token. "Both" is never itself stored on a Code row;
        it only exists as an input value here to mean "make 2 rows."
    Returns the list of tokens created (1 or 2 entries — same value
    twice when code_type is "Both", since both rows share one token)."""
    token = _unique_token()
    types_to_create = ["QR", "Barcode"] if code_type == "Both" else [code_type]

    tokens = []
    for t in types_to_create:
        code = Code(token=token, batch_no=batch.batch_no, code_type=t)
        db.session.add(code)
        db.session.flush()
        code.payload = code.build_payload()
        tokens.append(token)

    return tokens