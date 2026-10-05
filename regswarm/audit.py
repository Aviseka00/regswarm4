"""Tamper-evident audit trail: every agent action is appended to a hash chain
(each entry's hash covers the previous entry's hash), so any later edit or
deletion breaks verification. This is the basis for ALCOA+ style traceability
and the Part 11 audit-trail requirement in the production build."""
import datetime
import hashlib
import json
import threading

_lock = threading.Lock()


def _h(prev, ts, case_id, actor, action, detail):
    blob = "|".join([prev or "", ts, case_id, actor, action, detail])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def append(con, case_id, actor, action, detail=None):
    detail_s = json.dumps(detail or {}, sort_keys=True, ensure_ascii=False)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
    with _lock:
        row = con.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else ""
        h = _h(prev, ts, case_id, actor, action, detail_s)
        con.execute("INSERT INTO audit_log(ts, case_id, actor, action, detail, prev_hash, hash) VALUES(?,?,?,?,?,?,?)",
                    (ts, case_id, actor, action, detail_s, prev, h))
        con.commit()
    return h


def verify_chain(con):
    """Recompute the whole chain. Returns (ok, n_entries, first_bad_seq)."""
    prev, n = "", 0
    for r in con.execute("SELECT * FROM audit_log ORDER BY seq"):
        n += 1
        if r["prev_hash"] != prev or r["hash"] != _h(prev, r["ts"], r["case_id"], r["actor"], r["action"], r["detail"]):
            return False, n, r["seq"]
        prev = r["hash"]
    return True, n, None


def entries(con, case_id, limit=500):
    return [dict(r) for r in con.execute(
        "SELECT seq, ts, actor, action, detail, hash FROM audit_log WHERE case_id=? ORDER BY seq LIMIT ?",
        (case_id, limit))]
