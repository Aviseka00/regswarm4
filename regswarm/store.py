"""Persist completed/error run snapshots so review survives a restart."""
import json

SCHEMA = """CREATE TABLE IF NOT EXISTS run_snapshots(
 run_id TEXT PRIMARY KEY, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, payload TEXT NOT NULL
)"""
FIELDS = ("id", "case", "mode", "status", "version", "score", "signature", "document", "draft",
          "claim_res", "events", "case_context", "review_packet", "metrics")


def save(con, run):
    con.execute(SCHEMA)
    payload = json.dumps({k: getattr(run, k, None) for k in FIELDS}, ensure_ascii=False)
    con.execute("INSERT INTO run_snapshots(run_id,payload) VALUES(?,?) ON CONFLICT(run_id) DO UPDATE SET payload=excluded.payload, updated_at=CURRENT_TIMESTAMP",
                (run.id, payload))
    con.commit()


def load(con, run_id):
    from .pipeline import Run
    con.execute(SCHEMA)
    row = con.execute("SELECT payload FROM run_snapshots WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        return None
    data = json.loads(row[0])
    run = Run(data["id"], data["case"], data["mode"])
    for key in FIELDS:
        setattr(run, key, data[key])
    return run


def recent(con, production_only=False):
    con.execute(SCHEMA)
    result = []
    for row in con.execute("SELECT run_id,updated_at,payload FROM run_snapshots ORDER BY updated_at DESC LIMIT 30"):
        data = json.loads(row["payload"])
        if production_only and (data["mode"] != "live" or data["case"].get("synthetic") is not False):
            continue
        result.append({"id": row["run_id"], "updated_at": row["updated_at"], "status": data["status"],
                       "title": data["case"]["title"], "version": data["version"]})
    return result


def recover_interrupted(con):
    from .pipeline import Run
    con.execute(SCHEMA)
    rows = con.execute("SELECT payload FROM run_snapshots").fetchall()
    for row in rows:
        data = json.loads(row["payload"])
        if data.get("status") not in ("running", "queued"):
            continue
        run = Run(data["id"], data["case"], data["mode"])
        for key in FIELDS:
            setattr(run, key, data[key])
        run.status = "interrupted"
        run.emit("error", message="Processing was interrupted by a server restart. Start a new run; partial output cannot be approved.")
        save(con, run)
